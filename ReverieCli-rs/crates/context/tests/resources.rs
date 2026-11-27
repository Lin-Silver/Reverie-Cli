use reverie_context::resources::{self, Asset, Manifest, Model, Runtime};
use serde_json::json;
use std::{collections::BTreeMap, fs, path::Path};

fn fixture(directory: &Path) -> String {
    let mut files = BTreeMap::new();
    for name in ["embedding", "reranker"] {
        fs::create_dir_all(directory.join(name)).unwrap();
        for file in [
            "model.onnx",
            "tokenizer.json",
            "config.json",
            "special_tokens_map.json",
            "tokenizer_config.json",
        ] {
            fs::write(directory.join(name).join(file), b"resource fixture bytes").unwrap();
            let path = format!("{name}/{file}");
            files.insert(
                path.clone(),
                Asset {
                    bytes: 22,
                    sha256: resources::hash_file(&directory.join(path)).unwrap(),
                },
            );
        }
    }
    fs::create_dir_all(directory.join("runtime")).unwrap();
    let mut binary = [0u8; 128];
    match std::env::consts::OS {
        "windows" => {
            binary[..2].copy_from_slice(b"MZ");
            binary[60..64].copy_from_slice(&64u32.to_le_bytes());
            binary[64..68].copy_from_slice(b"PE\0\0");
            binary[68..70].copy_from_slice(&0x8664u16.to_le_bytes());
        }
        "linux" => {
            binary[..6].copy_from_slice(b"\x7fELF\x02\x01");
            binary[18..20].copy_from_slice(&62u16.to_le_bytes());
        }
        "macos" => {
            binary[..4].copy_from_slice(b"\xcf\xfa\xed\xfe");
            let architecture = if cfg!(target_arch = "aarch64") {
                0x0100000cu32
            } else {
                0x01000007u32
            };
            binary[4..8].copy_from_slice(&architecture.to_le_bytes());
        }
        _ => panic!("unsupported fixture platform"),
    }
    fs::write(directory.join("runtime/library"), binary).unwrap();
    fs::write(directory.join("LICENSE"), b"fixture license").unwrap();
    for name in ["runtime/library", "LICENSE"] {
        files.insert(
            name.into(),
            Asset {
                bytes: fs::metadata(directory.join(name)).unwrap().len(),
                sha256: resources::hash_file(&directory.join(name)).unwrap(),
            },
        );
    }
    let model = |id: &str, revision: &str, directory: &str| Model {
        id: id.into(),
        revision: revision.into(),
        onnx: format!("{directory}/model.onnx"),
        tokenizer_directory: directory.into(),
        max_length: 512,
        precision: "fp32".into(),
    };
    let manifest = Manifest {
        schema: "reverie.semantic-resource.v1".into(),
        version: "fixture-v1".into(),
        platform: std::env::consts::OS.into(),
        architecture: std::env::consts::ARCH.into(),
        dimensions: 384,
        runtime: Runtime {
            version: "1.31.0".into(),
            api_version: 24,
            library: "runtime/library".into(),
        },
        embedding: model(
            "intfloat/multilingual-e5-small",
            resources::E5_REVISION,
            "embedding",
        ),
        reranker: model(
            "BAAI/bge-reranker-base",
            resources::BGE_REVISION,
            "reranker",
        ),
        files,
        licenses: vec!["LICENSE".into()],
        provenance: json!({"purpose":"Resource validation fixture; no model inference"}),
    };
    fs::write(
        directory.join("manifest.json"),
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();
    resources::hash_file(&directory.join("manifest.json")).unwrap()
}

#[test]
fn offline_staging_verifies_actual_bytes_and_does_not_activate() {
    let directory = tempfile::tempdir().unwrap();
    let source = directory.path().join("source");
    fs::create_dir(&source).unwrap();
    let digest = fixture(&source);
    let store = directory.path().join("store");
    let bundle = resources::stage(&store, &source, &digest, &|| false).unwrap();
    assert!(bundle.directory.starts_with(store.canonicalize().unwrap()));
    assert_eq!(bundle.digest, digest);
    assert!(!store.join("active.json").exists());
    assert!(resources::verify(&source, &"0".repeat(64), &|| false).is_err());
    fs::write(
        bundle.directory.join("embedding/model.onnx"),
        b"tampered fixture bytes",
    )
    .unwrap();
    assert!(resources::stage(&store, &source, &digest, &|| false).is_err());
    fs::write(source.join("runtime/library"), b"damaged").unwrap();
    assert!(resources::verify(&source, &digest, &|| false).is_err());
}

#[test]
fn resources_reject_traversal_incompatible_contracts_and_cancelled_copy() {
    let directory = tempfile::tempdir().unwrap();
    let digest = fixture(directory.path());
    assert!(resources::verify(directory.path(), &digest, &|| true).is_err());
    for name in [
        "../LICENSE",
        "/LICENSE",
        "runtime/../LICENSE",
        "C:/LICENSE",
        "runtime\\library",
        "LICENSE.",
    ] {
        assert!(
            resources::asset_path(directory.path(), name).is_err(),
            "{name}"
        );
    }
    let path = directory.path().join("manifest.json");
    let mut manifest: Manifest = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    manifest.dimensions = 768;
    fs::write(&path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    let digest = resources::hash_file(&path).unwrap();
    assert!(resources::verify(directory.path(), &digest, &|| false).is_err());
}
