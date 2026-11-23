//! Local inference; no hub client, cloud call or implicit resource download.
use crate::{
    Result,
    resources::{self, VerifiedBundle},
};
use fastembed::{
    AutoDevicePolicy, InitOptionsUserDefined, Pooling, QuantizationMode,
    RerankInitOptionsUserDefined, TextEmbedding, TextRerank, TokenizerFiles,
    UserDefinedEmbeddingModel, UserDefinedRerankingModel,
};
use ort::{environment::Environment, ep::ExecutionProviderDispatch};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    sync::{Mutex, MutexGuard},
    time::Instant,
};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Device {
    #[default]
    Cpu,
    Cuda,
    DirectMl,
    CoreMl,
}

#[derive(Clone)]
struct RuntimeLease {
    digest: String,
    directory: std::path::PathBuf,
    environment: Environment,
}
static RUNTIME: Mutex<Option<RuntimeLease>> = Mutex::new(None);

fn lock<T>(value: &Mutex<T>) -> Result<MutexGuard<'_, T>> {
    value
        .lock()
        .map_err(|_| "Semantic model lock was poisoned.".into())
}

pub fn runtime_directory() -> Result<Option<std::path::PathBuf>> {
    Ok(lock(&RUNTIME)?
        .as_ref()
        .map(|runtime| runtime.directory.clone()))
}

fn environment(bundle: &VerifiedBundle) -> Result<Environment> {
    let library = &bundle.manifest.runtime.library;
    let digest = &bundle.manifest.files[library].sha256;
    let mut current = lock(&RUNTIME)?;
    if let Some(runtime) = current.as_ref() {
        if &runtime.digest != digest {
            return Err("Changing the loaded ORT library requires restarting the kernel; the previous library remains pinned.".into());
        }
        return Ok(runtime.environment.clone());
    }
    let path = resources::asset_path(&bundle.directory, library)?;
    if resources::hash_file(&path)? != *digest {
        return Err("ORT runtime content changed before loading.".into());
    }
    let environment = ort::init_from(&path)?
        .with_name("Reverie Local Semantic")
        .build()?;
    *current = Some(RuntimeLease {
        digest: digest.clone(),
        directory: bundle.directory.clone(),
        environment: environment.clone(),
    });
    Ok(environment)
}

fn read(bundle: &VerifiedBundle, name: &str) -> Result<Vec<u8>> {
    let asset = bundle
        .manifest
        .files
        .get(name)
        .ok_or("Semantic file is not in the manifest.")?;
    let bytes = fs::read(resources::asset_path(&bundle.directory, name)?)?;
    let digest: String = Sha256::digest(&bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    if bytes.len() as u64 != asset.bytes || digest != asset.sha256 {
        return Err(format!("Semantic asset changed before use: {name}").into());
    }
    Ok(bytes)
}

fn tokenizer(bundle: &VerifiedBundle, directory: &str) -> Result<TokenizerFiles> {
    Ok(TokenizerFiles {
        tokenizer_file: read(bundle, &format!("{directory}/tokenizer.json"))?,
        config_file: read(bundle, &format!("{directory}/config.json"))?,
        special_tokens_map_file: read(bundle, &format!("{directory}/special_tokens_map.json"))?,
        tokenizer_config_file: read(bundle, &format!("{directory}/tokenizer_config.json"))?,
    })
}

fn providers(device: Device) -> Result<Vec<ExecutionProviderDispatch>> {
    match device {
        Device::Cpu => Ok(Vec::new()),
        Device::Cuda if cfg!(any(target_os = "windows", target_os = "linux")) => {
            Ok(vec![ort::ep::CUDA::default().build().error_on_failure()])
        }
        Device::DirectMl if cfg!(target_os = "windows") => Ok(vec![
            ort::ep::DirectML::default().build().error_on_failure(),
        ]),
        Device::CoreMl if cfg!(target_os = "macos") => {
            Ok(vec![ort::ep::CoreML::default().build().error_on_failure()])
        }
        _ => Err("The requested GPU provider is incompatible with this platform.".into()),
    }
}

#[derive(Default)]
struct ModelState {
    embedding: Option<TextEmbedding>,
    reranker: Option<TextRerank>,
    effective: Device,
    fallback: Option<String>,
}

pub struct LocalModels {
    pub bundle: VerifiedBundle,
    requested: Device,
    threads: usize,
    state: Mutex<ModelState>,
}

impl LocalModels {
    pub fn new(bundle: VerifiedBundle, device: Device, threads: usize) -> Result<Self> {
        if threads == 0 {
            return Err("Semantic intra-op threads must be positive.".into());
        }
        Ok(Self {
            bundle,
            requested: device,
            threads,
            state: Mutex::new(ModelState {
                effective: device,
                ..Default::default()
            }),
        })
    }

    pub fn status(&self) -> Result<Value> {
        let state = lock(&self.state)?;
        Ok(
            json!({"available":true,"installed":true,"status":if state.embedding.is_some()&&state.reranker.is_some(){"ready"}else{"on_demand"},
            "manifest_sha256":self.bundle.digest,"version":self.bundle.manifest.version,"dimensions":self.bundle.manifest.dimensions,
            "requested_device":self.requested,"effective_device":state.effective,"fallback_reason":state.fallback,"intra_threads":self.threads,
            "embedding_loaded":state.embedding.is_some(),"reranker_loaded":state.reranker.is_some(),"embedding_precision":self.bundle.manifest.embedding.precision,"reranker_precision":self.bundle.manifest.reranker.precision}),
        )
    }

    pub fn unload(&self) -> Result<()> {
        let mut state = lock(&self.state)?;
        state.embedding = None;
        state.reranker = None;
        Ok(())
    }

    fn embedding(&self, device: Device) -> Result<TextEmbedding> {
        let model = &self.bundle.manifest.embedding;
        let embedding = UserDefinedEmbeddingModel::new(
            read(&self.bundle, &model.onnx)?,
            tokenizer(&self.bundle, &model.tokenizer_directory)?,
        )
        .with_pooling(Pooling::Mean)
        .with_quantization(if model.precision == "dynamic-int8" {
            QuantizationMode::Dynamic
        } else {
            QuantizationMode::None
        });
        let options = InitOptionsUserDefined::new()
            .with_environment(environment(&self.bundle)?)
            .with_intra_threads(self.threads)
            .with_max_length(model.max_length)
            .with_auto_device(AutoDevicePolicy::PreferCPU)
            .with_execution_providers(providers(device)?);
        Ok(TextEmbedding::try_new_from_user_defined(
            embedding, options,
        )?)
    }

    fn reranker(&self, device: Device) -> Result<TextRerank> {
        let model = &self.bundle.manifest.reranker;
        let reranker = UserDefinedRerankingModel::new(
            read(&self.bundle, &model.onnx)?,
            tokenizer(&self.bundle, &model.tokenizer_directory)?,
        );
        let options = RerankInitOptionsUserDefined::new()
            .with_environment(environment(&self.bundle)?)
            .with_intra_threads(self.threads)
            .with_max_length(model.max_length)
            .with_auto_device(AutoDevicePolicy::PreferCPU)
            .with_execution_providers(providers(device)?);
        Ok(TextRerank::try_new_from_user_defined(reranker, options)?)
    }

    fn fallback(state: &mut ModelState, error: impl ToString) {
        state.embedding = None;
        state.reranker = None;
        state.effective = Device::Cpu;
        state.fallback = Some(error.to_string());
    }

    fn ensure_embedding(&self, state: &mut ModelState) -> Result<()> {
        if state.embedding.is_none() {
            match self.embedding(state.effective) {
                Ok(model) => state.embedding = Some(model),
                Err(error) if state.effective != Device::Cpu => {
                    Self::fallback(state, error);
                    state.embedding = Some(self.embedding(Device::Cpu)?);
                }
                Err(error) => return Err(error),
            }
        }
        Ok(())
    }

    fn ensure_reranker(&self, state: &mut ModelState) -> Result<()> {
        if state.reranker.is_none() {
            match self.reranker(state.effective) {
                Ok(model) => state.reranker = Some(model),
                Err(error) if state.effective != Device::Cpu => {
                    Self::fallback(state, error);
                    state.reranker = Some(self.reranker(Device::Cpu)?);
                }
                Err(error) => return Err(error),
            }
        }
        Ok(())
    }

    pub fn embed(
        &self,
        texts: &[String],
        query: bool,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Vec<Vec<f32>>> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }
        if cancelled() {
            return Err("Semantic embedding cancelled.".into());
        }
        let mut state = lock(&self.state)?;
        self.ensure_embedding(&mut state)?;
        let inputs = texts
            .iter()
            .map(|text| format!("{}: {text}", if query { "query" } else { "passage" }))
            .collect::<Vec<_>>();
        let mut vectors = Vec::with_capacity(inputs.len());
        for batch in inputs.chunks(8) {
            if cancelled() {
                return Err("Semantic embedding cancelled.".into());
            }
            let result = state
                .embedding
                .as_mut()
                .ok_or("Embedding is not loaded.")?
                .embed(batch, Some(batch.len()));
            let result = match result {
                Ok(result) => result,
                Err(error) if state.effective != Device::Cpu => {
                    Self::fallback(&mut state, error);
                    self.ensure_embedding(&mut state)?;
                    state
                        .embedding
                        .as_mut()
                        .ok_or("CPU embedding is not loaded.")?
                        .embed(batch, Some(batch.len()))?
                }
                Err(error) => return Err(error.into()),
            };
            if result.len() != batch.len() {
                return Err("Semantic embedding count mismatch.".into());
            }
            for mut vector in result {
                if vector.len() != 384 || vector.iter().any(|value| !value.is_finite()) {
                    return Err("Invalid semantic vector.".into());
                }
                let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
                if !norm.is_finite() || norm <= 0.0 {
                    return Err("Semantic embedding has invalid norm.".into());
                }
                vector.iter_mut().for_each(|value| *value /= norm);
                vectors.push(vector);
            }
        }
        if cancelled() {
            return Err("Semantic embedding cancelled.".into());
        }
        Ok(vectors)
    }

    pub fn rerank(
        &self,
        query: &str,
        documents: &[String],
        cancelled: &impl Fn() -> bool,
    ) -> Result<Vec<(usize, f32)>> {
        if documents.is_empty() {
            return Ok(Vec::new());
        }
        if cancelled() {
            return Err("Semantic reranking cancelled.".into());
        }
        let mut state = lock(&self.state)?;
        self.ensure_reranker(&mut state)?;
        let result = state
            .reranker
            .as_mut()
            .ok_or("Reranker is not loaded.")?
            .rerank(query.to_owned(), documents, false, Some(16));
        let result = match result {
            Ok(result) => result,
            Err(error) if state.effective != Device::Cpu => {
                Self::fallback(&mut state, error);
                self.ensure_reranker(&mut state)?;
                state
                    .reranker
                    .as_mut()
                    .ok_or("CPU reranker is not loaded.")?
                    .rerank(query.to_owned(), documents, false, Some(16))?
            }
            Err(error) => return Err(error.into()),
        };
        if cancelled() {
            return Err("Semantic reranking cancelled.".into());
        }
        let mut seen = std::collections::BTreeSet::new();
        if result.len() != documents.len()
            || result.iter().any(|item| {
                item.index >= documents.len() || !seen.insert(item.index) || !item.score.is_finite()
            })
        {
            return Err("Invalid neural reranking result.".into());
        }
        Ok(result
            .into_iter()
            .map(|item| (item.index, item.score))
            .collect())
    }

    pub fn probe(&self) -> Result<Value> {
        let started = Instant::now();
        let vectors = self.embed(
            &[
                "How can I save player progress?".into(),
                "把游戏进度写入本地存档文件。".into(),
            ],
            false,
            &|| false,
        )?;
        let scores = self.rerank(
            "How can I save player progress?",
            &[
                "把游戏进度写入本地存档文件。".into(),
                "The menu background is blue.".into(),
            ],
            &|| false,
        )?;
        Ok(
            json!({"loaded":true,"models":self.status()?,"ort_build_info":ort::info(),"vector_dimensions":vectors.iter().map(Vec::len).collect::<Vec<_>>(),
            "vector_norms":vectors.iter().map(|vector|vector.iter().map(|value|value*value).sum::<f32>().sqrt()).collect::<Vec<_>>(),"reranked":scores,"elapsed_ms":started.elapsed().as_secs_f64()*1000.0}),
        )
    }
}
