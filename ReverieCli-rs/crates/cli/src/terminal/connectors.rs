use super::{Input, PanelKind, Tui, display_text};
use reverie_core::Result;
use reverie_protocol::{ConnectorDiscovery, Reply, StartedConnectorAuthorization};
use serde_json::{Value, json};
use std::process::{Command, Stdio};

#[derive(Default)]
pub(super) struct ConnectorUiState {
    discovery: Option<ConnectorDiscovery>,
    flow: Option<AuthorizationFlow>,
    pub background: bool,
    waiting_authorization: Option<String>,
}
struct AuthorizationFlow {
    discovery: ConnectorDiscovery,
    choice: Value,
    dynamic: bool,
    client_secret: String,
    registration_token: String,
}

pub(super) fn private_command(text: &str) -> bool {
    let mut words = text.split_whitespace();
    match (words.next(), words.next()) {
        (Some("/connectors" | "/connector"), Some("key" | "api-key")) => true,
        (Some("/modelscope"), Some(action)) => {
            matches!(
                action.to_ascii_lowercase().as_str(),
                "key" | "api-key" | "apikey" | "login"
            )
        }
        _ => false,
    }
}
pub(super) fn masked_input(input: &Input) -> Input {
    let mask = |text: &str| {
        text.chars()
            .map(|ch| if ch == '\n' { '\n' } else { '*' })
            .collect::<String>()
    };
    Input {
        text: mask(&input.text),
        cursor: mask(&input.text[..input.cursor]).len(),
    }
}
fn open_authorization(url: &str) -> Result<()> {
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err("The returned authorization URL is not HTTP(S).".into());
    }
    #[cfg(target_os = "windows")]
    let mut command = {
        use std::os::windows::process::CommandExt;
        let mut command = Command::new("rundll32.exe");
        command
            .args(["url.dll,FileProtocolHandler", url])
            .creation_flags(0x08000000);
        command
    };
    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("open");
        command.arg(url);
        command
    };
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    let mut command = {
        let mut command = Command::new("xdg-open");
        command.arg(url);
        command
    };
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    std::thread::spawn(move || {
        let _ = child.wait();
    });
    Ok(())
}

impl Tui {
    fn start_connector_operation(&mut self, action: &str, payload: Value) -> Result<()> {
        self.start_plugin_operation(action, payload)?;
        self.connectors.background = true;
        self.status = format!("MCP / Connector {action} · /connectors stop");
        Ok(())
    }
    pub(super) async fn stop_connector_operation(&mut self) -> Result<()> {
        if let Some(id) = self.connectors.waiting_authorization.clone() {
            self.request(
                "cancelConnectorAuthorization",
                json!({"authorization_id":id}),
            )
            .await?;
        }
        self.stop_context_operation().await
    }
    pub(super) fn print_connector_reply(&mut self, reply: &Reply) -> Result<()> {
        self.connectors.background = false;
        self.connectors.waiting_authorization = None;
        if reply.kind == "error" {
            return self
                .screen
                .print(&display_text(
                    reply.fields["error"]
                        .as_str()
                        .unwrap_or("MCP / Connector operation failed."),
                ))
                .map_err(Into::into);
        }
        let connector = reply.fields.get("connector").unwrap_or(&Value::Null);
        if connector.get("authorization_url").is_some() {
            let started: StartedConnectorAuthorization = serde_json::from_value(connector.clone())?;
            if open_authorization(&started.authorization_url).is_err() {
                self.screen.print("The browser launcher failed. Cancel this authorization and begin a new reviewed flow from a supported desktop.")?;
            }
            // Only the one-time launch uses the authorization URL. Scrollback holds public identifiers.
            self.screen.print(&display_text(&format!(
                "Authorization started for {}\nResource: {}\nIssuer: {}\nScopes: {}\nAuthorization ID: {}\n/connectors complete {} {}\n/connectors cancel {}",
                started.server_id,started.resource,started.issuer,started.scopes.join(" "),started.authorization_id,started.server_id,started.authorization_id,started.authorization_id
            )))?;
        } else if connector.get("discovery_id").is_some() {
            let discovery: ConnectorDiscovery = serde_json::from_value(connector.clone())?;
            self.screen.print(&display_text(&format!("Connector discovery:\n{}\nReview with /connectors authorize {} {}. Discovery did not register a client or exchange credentials.",serde_json::to_string_pretty(&discovery)?,discovery.server_id,discovery.discovery_id)))?;
            self.connectors.discovery = Some(discovery);
        } else if !connector.is_null() {
            self.screen
                .print(&display_text(&serde_json::to_string_pretty(connector)?))?;
        } else {
            self.screen.print(&display_text(&serde_json::to_string_pretty(&json!({"mcp":reply.fields.get("mcp"),"diagnostics":reply.fields.get("mcp_diagnostics"),"authorization_diagnostics":reply.fields.get("authorization_diagnostics")}))?))?;
        }
        Ok(())
    }
    fn connector_input(
        &mut self,
        stage: &str,
        title: String,
        initial: &str,
        secret: bool,
        source: Value,
    ) {
        let mut source = source;
        source["stage"] = json!(stage);
        self.panel(
            if secret {
                PanelKind::ConnectorSecret
            } else {
                PanelKind::ConnectorInput
            },
            title,
            vec!["Cancel".into(), "Continue with this input".into()],
            source,
            false,
        );
        self.input.insert(initial);
        if !initial.is_empty() {
            self.panel.as_mut().unwrap().selected = 1;
        }
    }
    fn authorization_method_panel(&mut self) -> Result<()> {
        let flow = self
            .connectors
            .flow
            .as_ref()
            .ok_or("No reviewed Connector discovery is available.")?;
        let issuer = flow
            .discovery
            .authorization_servers
            .iter()
            .find(|issuer| issuer.issuer == flow.choice["issuer"])
            .ok_or("Select a discovered authorization server.")?;
        let methods = issuer
            .token_endpoint_auth_methods_supported
            .iter()
            .filter(|method| {
                matches!(
                    method.as_str(),
                    "none" | "client_secret_basic" | "client_secret_post"
                )
            })
            .cloned()
            .collect::<Vec<_>>();
        if methods.is_empty() {
            return Err("This issuer has no supported client authentication method.".into());
        }
        let mut options = vec!["Cancel".into()];
        options.extend(methods.clone());
        self.panel(
            PanelKind::ConnectorChoice,
            "Choose OAuth client authentication method".into(),
            options,
            json!({"stage":"method","methods":methods}),
            false,
        );
        Ok(())
    }
    fn authorization_redirect_panel(&mut self) {
        self.connector_input(
            "redirect",
            "Optional clean HTTP loopback callback URI; leave empty for an automatic local port"
                .into(),
            "",
            false,
            json!({}),
        );
    }
    fn review_authorization(&mut self) -> Result<()> {
        let flow = self
            .connectors
            .flow
            .as_ref()
            .ok_or("No Connector authorization is being reviewed.")?;
        let issuer = flow
            .discovery
            .authorization_servers
            .iter()
            .find(|issuer| issuer.issuer == flow.choice["issuer"])
            .ok_or("Select a discovered authorization server.")?;
        let summary = json!({"server_id":flow.discovery.server_id,"resource":flow.discovery.resource,"issuer":issuer.issuer,"scopes":flow.choice["scopes"],"client_id":flow.choice["client_id"],"client_auth_method":flow.choice["client_auth_method"],"redirect_uri":flow.choice["redirect_uri"],"registration":if flow.dynamic{"dynamic"}else{"preregistered"},"registration_endpoint":if flow.dynamic{issuer.registration_endpoint.as_deref()}else{None},"client_secret_supplied":!flow.client_secret.is_empty(),"registration_token_supplied":!flow.registration_token.is_empty(),"expires_at":flow.discovery.expires_at});
        self.screen.print(&display_text(&format!(
            "Review Connector authorization:\n{}",
            serde_json::to_string_pretty(&summary)?
        )))?;
        self.panel(PanelKind::ConnectorConfirmation,"Confirm the resource, issuer, scopes, registration and client shown above? Browser authorization begins only after confirmation.".into(),vec!["Cancel".into(),"Confirm and open browser authorization".into()],json!({"stage":"authorize"}),false);
        Ok(())
    }
    pub(super) async fn submit_connector_panel(&mut self, cancelled: bool) -> Result<()> {
        let panel = self.panel.take().ok_or("No Connector panel is open.")?;
        let text = self.input.take();
        self.input = panel.draft;
        if cancelled || panel.selected == 0 {
            self.connectors.flow = None;
            return self.refresh().await;
        }
        let stage = panel.source["stage"].as_str().unwrap_or("");
        match stage {
            "request" => {
                let action = panel.source["action"]
                    .as_str()
                    .ok_or("Missing reviewed MCP operation.")?;
                self.start_connector_operation(action, panel.source["payload"].clone())?;
            }
            "key" => {
                if text.is_empty() {
                    return Err(
                        "Supply the complete credential header value in the masked panel.".into(),
                    );
                }
                self.start_connector_operation("setConnectorApiKey",json!({"server_id":panel.source["server_id"],"expected_fingerprint":panel.source["expected_fingerprint"],"header":panel.source["header"],"secret":text,"confirmed":true}))?;
            }
            "issuer" => {
                let flow = self
                    .connectors
                    .flow
                    .as_mut()
                    .ok_or("No Connector discovery is being reviewed.")?;
                let issuer = flow
                    .discovery
                    .authorization_servers
                    .get(panel.selected - 1)
                    .ok_or("Select a discovered issuer.")?;
                flow.choice["issuer"] = json!(issuer.issuer);
                let scopes = flow.discovery.required_scopes.join(" ");
                self.connector_input("scopes","Enter the exact scopes to approve, separated by spaces. Required scopes must be included.".into(),&scopes,false,json!({}));
            }
            "scopes" => {
                let flow = self
                    .connectors
                    .flow
                    .as_mut()
                    .ok_or("No Connector authorization is being reviewed.")?;
                let mut scopes = text
                    .split_whitespace()
                    .map(str::to_owned)
                    .collect::<Vec<_>>();
                scopes.sort();
                scopes.dedup();
                if !flow
                    .discovery
                    .required_scopes
                    .iter()
                    .all(|required| scopes.contains(required))
                {
                    return Err(
                        "The approved scopes must include every discovered required scope.".into(),
                    );
                }
                flow.choice["scopes"] = json!(scopes);
                let issuer = flow
                    .discovery
                    .authorization_servers
                    .iter()
                    .find(|issuer| issuer.issuer == flow.choice["issuer"])
                    .ok_or("Select a discovered issuer.")?;
                let dynamic = issuer.registration_endpoint.is_some();
                let options = if dynamic {
                    vec![
                        "Cancel".into(),
                        "Dynamically register a client".into(),
                        "Use a preregistered client".into(),
                    ]
                } else {
                    vec!["Cancel".into(), "Use a preregistered client".into()]
                };
                self.panel(
                    PanelKind::ConnectorChoice,
                    "Choose OAuth client registration".into(),
                    options,
                    json!({"stage":"registration","dynamic_available":dynamic}),
                    false,
                );
            }
            "registration" => {
                let flow = self
                    .connectors
                    .flow
                    .as_mut()
                    .ok_or("No Connector authorization is being reviewed.")?;
                flow.dynamic = panel.source["dynamic_available"] == true && panel.selected == 1;
                if flow.dynamic {
                    self.authorization_method_panel()?;
                } else {
                    self.connector_input(
                        "client_id",
                        "Enter the preregistered OAuth Client ID".into(),
                        "",
                        false,
                        json!({}),
                    );
                }
            }
            "client_id" => {
                if text.trim().is_empty() {
                    return Err("A preregistered Client ID is required.".into());
                }
                self.connectors
                    .flow
                    .as_mut()
                    .ok_or("No Connector authorization is being reviewed.")?
                    .choice["client_id"] = json!(text.trim());
                self.authorization_method_panel()?;
            }
            "method" => {
                let method = panel.source["methods"][panel.selected - 1]
                    .as_str()
                    .ok_or("Select a supported authentication method.")?;
                let flow = self
                    .connectors
                    .flow
                    .as_mut()
                    .ok_or("No Connector authorization is being reviewed.")?;
                flow.choice["client_auth_method"] = json!(method);
                if flow.dynamic {
                    self.connector_input("registration_token","Optional registration token; input is masked and never stored in prompt history".into(),"",true,json!({}));
                } else if method != "none" {
                    self.connector_input(
                        "client_secret",
                        "OAuth Client secret; input is masked and never stored in prompt history"
                            .into(),
                        "",
                        true,
                        json!({}),
                    );
                } else {
                    self.authorization_redirect_panel();
                }
            }
            "client_secret" => {
                if text.is_empty() {
                    return Err("The chosen method requires a Client secret.".into());
                }
                self.connectors
                    .flow
                    .as_mut()
                    .ok_or("No Connector authorization is being reviewed.")?
                    .client_secret = text;
                self.authorization_redirect_panel();
            }
            "registration_token" => {
                self.connectors
                    .flow
                    .as_mut()
                    .ok_or("No Connector authorization is being reviewed.")?
                    .registration_token = text;
                self.authorization_redirect_panel();
            }
            "redirect" => {
                if !text.trim().is_empty() {
                    self.connectors
                        .flow
                        .as_mut()
                        .ok_or("No Connector authorization is being reviewed.")?
                        .choice["redirect_uri"] = json!(text.trim());
                }
                self.review_authorization()?;
            }
            "authorize" => {
                let mut flow = self
                    .connectors
                    .flow
                    .take()
                    .ok_or("No Connector authorization is being reviewed.")?;
                flow.choice["confirmed"] = json!(true);
                if !flow.client_secret.is_empty() {
                    flow.choice["client_secret"] = json!(flow.client_secret);
                }
                if !flow.registration_token.is_empty() {
                    flow.choice["registration_token"] = json!(flow.registration_token);
                }
                self.start_connector_operation("authorizeConnector",json!({"server_id":flow.discovery.server_id,"discovery_id":flow.discovery.discovery_id,"choice":flow.choice}))?;
            }
            _ => return Err("Unknown Connector panel step.".into()),
        }
        Ok(())
    }
    fn confirm_connector_request(&mut self, action: &str, title: String, payload: Value) {
        self.panel(
            PanelKind::ConnectorConfirmation,
            title,
            vec!["Cancel".into(), "Confirm this inspected operation".into()],
            json!({"stage":"request","action":action,"payload":payload}),
            false,
        );
    }
    pub(super) async fn mcp_command(&mut self, args: &[String]) -> Result<()> {
        let operation = args.first().map(String::as_str).unwrap_or("list");
        if self.active.is_some() && matches!(operation, "configure" | "trust" | "remove") {
            return Err(
                "Finish or stop the active run before opening an MCP confirmation panel.".into(),
            );
        }
        if operation == "stop" {
            return self.stop_connector_operation().await;
        }
        if operation == "help" {
            return self.screen.print("/mcp list · inspect <id-or-name>\n/mcp configure <name> <complete-configuration-json-file>\n/mcp trust <id-or-name> · untrust <id-or-name>\n/mcp enable <id-or-name> · disable <id-or-name> · remove <id-or-name>\n/mcp refresh [server-id] · resource <server-id> <uri>\n/mcp prompt <server-id> <name> [arguments-json-file]\n/mcp stop\nConfiguration replacement preserves supplied fields and saves without trust. Trust binds the inspected fingerprint. Refresh discovers all effective services; a supplied ID invalidates only its cached client.").map_err(Into::into);
        }
        if operation == "refresh" {
            self.start_connector_operation("refreshMcp", json!({"server_id":args.get(1)}))?;
            return Ok(());
        }
        if operation == "resource" {
            let id = args.get(1).ok_or("Supply a server ID.")?;
            let uri = args.get(2).ok_or("Supply a resource URI.")?;
            self.start_connector_operation("readMcpResource", json!({"server_id":id,"uri":uri}))?;
            return Ok(());
        }
        if operation == "prompt" {
            let id = args.get(1).ok_or("Supply a server ID.")?;
            let name = args.get(2).ok_or("Supply an MCP prompt name.")?;
            let arguments = if let Some(path) = args.get(3) {
                serde_json::from_str::<Value>(&std::fs::read_to_string(
                    self.host.project_root()?.join(path),
                )?)?
            } else {
                json!({})
            };
            if !arguments.is_object() {
                return Err("Prompt arguments must be a JSON object.".into());
            }
            self.start_connector_operation(
                "getMcpPrompt",
                json!({"server_id":id,"name":name,"arguments":arguments}),
            )?;
            return Ok(());
        }
        let management = self.request("listMcp", json!({})).await?;
        if operation == "list" {
            self.screen
                .print(&display_text(&serde_json::to_string_pretty(&management)?))?;
            return Ok(());
        }
        let id = args
            .get(1)
            .ok_or("Supply a manual MCP name or a server ID from /mcp list.")?;
        if operation == "configure" {
            if args.len() != 3 {
                return Err("Use /mcp configure <name> <complete-configuration-json-file>; do not paste secrets into slash commands.".into());
            }
            let path = self.host.project_root()?.join(&args[2]);
            let raw = std::fs::read_to_string(&path)?;
            if raw.len() > 1024 * 1024 {
                return Err("MCP configuration exceeds 1 MiB.".into());
            }
            let mut configuration: Value = serde_json::from_str(&raw)?;
            if !configuration.is_object() {
                return Err("MCP configuration must be a JSON object.".into());
            }
            if configuration["trust"] == true {
                return Err("Save configuration without trust, then review its execution fingerprint separately.".into());
            }
            configuration["trust"] = json!(false);
            self.confirm_connector_request("configureMcp",format!("Add or completely replace manual MCP {id} from {}? Private values will not be printed. The saved configuration starts without trust.",display_text(&path.display().to_string())),json!({"name":id,"configuration":configuration,"expected_revision":management["mcp"]["revision"]}));
            return Ok(());
        }
        let server = management["servers"]
            .as_array()
            .and_then(|servers| {
                servers
                    .iter()
                    .find(|server| server["id"] == id.as_str() || server["name"] == id.as_str())
            })
            .cloned();
        if operation == "inspect" {
            let server = server
                .ok_or("MCP configuration was not found; inspect diagnostics in /mcp list.")?;
            self.screen
                .print(&display_text(&serde_json::to_string_pretty(&server)?))?;
            return Ok(());
        }
        let server = server
            .or_else(|| {
                management["mcp"]["servers"]
                    .as_array()
                    .and_then(|servers| {
                        servers.iter().find(|server| {
                            server["origin"] == "manual"
                                && (server["id"] == id.as_str() || server["name"] == id.as_str())
                        })
                    })
                    .cloned()
            })
            .ok_or("Manual MCP configuration was not found.")?;
        if server["origin"] != "manual" {
            return Err(
                "This MCP comes from a plugin. Manage its trust and enable state with /plugins."
                    .into(),
            );
        }
        let mut payload =
            json!({"name":server["name"],"expected_revision":management["mcp"]["revision"]});
        match operation {
            "trust" => {
                let fingerprint = server["fingerprint"]
                    .as_str()
                    .ok_or("Repair this invalid configuration before trusting it.")?;
                self.screen
                    .print(&display_text(&serde_json::to_string_pretty(&server)?))?;
                payload["trusted"] = json!(true);
                payload["fingerprint"] = json!(fingerprint);
                self.confirm_connector_request("setMcpTrust",format!("Trust exactly this MCP execution fingerprint for {id}? Enabling the service remains a separate action."),payload);
            }
            "remove" => {
                self.screen
                    .print(&display_text(&serde_json::to_string_pretty(&server)?))?;
                payload["confirmed"] = json!(true);
                self.confirm_connector_request("removeMcp",format!("Remove manual MCP {id}? Saved Connector credentials are managed separately."),payload);
            }
            "enable" | "disable" => {
                payload["enabled"] = json!(operation == "enable");
                self.start_connector_operation("setMcpEnabled", payload)?;
            }
            "untrust" => {
                payload["trusted"] = json!(false);
                self.start_connector_operation("setMcpTrust", payload)?;
            }
            _ => return Err("Unknown MCP command. Use /mcp help.".into()),
        }
        Ok(())
    }
    pub(super) async fn connectors_command(&mut self, args: &[String]) -> Result<()> {
        if self.active.is_some()
            && matches!(
                args.first().map(String::as_str),
                Some("authorize" | "key" | "api-key" | "revoke" | "clear")
            )
        {
            return Err(
                "Finish or stop the active run before opening a private Connector panel.".into(),
            );
        }
        match args.first().map(String::as_str).unwrap_or("list") {
            "list"|"status"=>{let reply=self.request("listConnectors",json!({})).await?;self.screen.print(&display_text(&serde_json::to_string_pretty(&reply)?))?;}
            "discover"=>{let id=args.get(1).ok_or("Supply a server ID from /mcp list.")?;self.start_connector_operation("discoverConnector",json!({"server_id":id}))?;}
            "authorize"=>{
                if self.background.is_some(){return Err("Finish the current operation before reviewing authorization.".into());}
                if args.len()!=3{return Err("Use /connectors authorize <server-id> <discovery-id>; the panel collects all client credentials privately.".into());}
                let discovery=self.connectors.discovery.as_ref().filter(|discovery|discovery.server_id==args[1]&&discovery.discovery_id==args[2]).cloned().ok_or("Run /connectors discover and use its current IDs in this terminal.")?;
                let mut options=vec!["Cancel".into()];options.extend(discovery.authorization_servers.iter().map(|issuer|issuer.issuer.clone()));
                if options.len()==1{return Err("This discovery contains no authorization server.".into());}
                self.connectors.flow=Some(AuthorizationFlow {discovery,choice:json!({}),dynamic:false,client_secret:String::new(),registration_token:String::new()});
                self.panel(PanelKind::ConnectorChoice,"Choose the discovered OAuth issuer; registration starts only after the final review".into(),options,json!({"stage":"issuer"}),false);
            }
            "complete"=>{if args.len()!=3{return Err("Use /connectors complete <server-id> <authorization-id>.".into());}self.start_connector_operation("completeConnectorAuthorization",json!({"server_id":args[1],"authorization_id":args[2]}))?;self.connectors.waiting_authorization=Some(args[2].clone());}
            "cancel"=>{let id=args.get(1).ok_or("Supply the public authorization ID.")?;self.request("cancelConnectorAuthorization",json!({"authorization_id":id})).await?;if self.connectors.waiting_authorization.as_deref()==Some(id){self.stop_context_operation().await?;}self.screen.print("Connector authorization cancellation requested.")?;}
            "key"|"api-key"=>{
                if !(2..=3).contains(&args.len()){return Err("Use /connectors key <server-id> [header-name]. Enter the secret only in the masked panel.".into());}
                let state=self.request("listMcp",json!({})).await?;
                let server=state["servers"].as_array().and_then(|servers|servers.iter().find(|server|server["id"]==args[1])).ok_or("The MCP configuration is not available.")?;
                if server["type"]=="stdio"||server["trust"]!=true||server["enabled"]!=true{return Err("Enable and explicitly trust a remote MCP configuration before using its credentials.".into());}
                let header=args.get(2).map(String::as_str).unwrap_or("Authorization");
                if header.is_empty() || !header.bytes().all(|byte|byte.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&byte)) {
                    return Err("Supply only a valid HTTP header name in the slash command; paste the credential into the masked panel.".into());
                }
                self.screen.print(&display_text(&serde_json::to_string_pretty(server)?))?;
                self.connector_input("key",format!("Approve using the complete {header} header value for {}? Input is masked. Authorization values include their scheme (for example Bearer).",server["url"].as_str().unwrap_or_default()),"",true,json!({"server_id":args[1],"expected_fingerprint":server["fingerprint"],"header":header}));
            }
            "revoke"|"clear"=>{
                let operation=args[0].as_str();let id=args.get(1).ok_or("Supply a Connector server ID.")?;
                let state=self.request("listConnectors",json!({})).await?;
                let connector=state["connectors"]["connectors"].as_array().and_then(|connectors|connectors.iter().find(|connector|connector["server_id"]==id.as_str())).ok_or("Connector state was not found.")?;
                self.screen.print(&display_text(&serde_json::to_string_pretty(connector)?))?;
                let title=if operation=="clear"{format!("Clear only local credentials for {id}? This will not request remote revocation and works even after configuration removal.")}else{format!("Revoke authorization for {id}? The remote revocation result is reported separately from local cleanup.")};
                self.confirm_connector_request(if operation=="clear"{"clearConnectorCredentials"}else{"revokeConnector"},title,json!({"server_id":id,"confirmed":true}));
            }
            "stop"=>self.stop_connector_operation().await?,
            "help"=>self.screen.print("/connectors list\n/connectors discover <server-id>\n/connectors authorize <server-id> <discovery-id>\n/connectors complete <server-id> <authorization-id>\n/connectors cancel <authorization-id>\n/connectors key <server-id> [header-name]\n/connectors revoke <server-id> · clear <server-id> · stop\nSecrets never belong in slash arguments. OAuth review uses masked Client secret / registration-token panels and a separate final confirmation. Pending public IDs remain visible with /connectors list.")?,
            _=>return Err("Unknown Connector command. Use /connectors help.".into()),
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn secrets_are_masked_with_a_valid_byte_cursor_and_newlines() {
        let input = Input {
            text: "Bearer 密钥😀\nend".into(),
            cursor: "Bearer 密钥😀".len(),
        };
        let masked = masked_input(&input);
        assert_eq!(masked.text, "**********\n***");
        assert_eq!(masked.cursor, 10);
        assert!(!masked.text.contains("Bearer"));
        assert!(masked.text.is_char_boundary(masked.cursor));
    }
    #[test]
    fn api_key_commands_are_excluded_even_when_an_invalid_secret_argument_is_added() {
        assert!(private_command(
            "/connectors key manual:test Authorization accidentally-pasted-secret"
        ));
        assert!(private_command("/connector api-key manual:test"));
        assert!(private_command("  /connectors key manual:test"));
        assert!(!private_command("/connectors list"));
    }
}
