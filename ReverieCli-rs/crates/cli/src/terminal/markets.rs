use super::{Tui, display_text};
use reverie_core::Result;
use reverie_protocol::Reply;
use serde_json::{Value, json};

impl Tui {
    pub(super) fn print_market_reply(&mut self, reply: &Reply) -> Result<()> {
        if reply.kind == "error" {
            return self
                .screen
                .print(&display_text(
                    reply.fields["error"]
                        .as_str()
                        .unwrap_or("Marketplace operation failed."),
                ))
                .map_err(Into::into);
        }
        self.print_market_entries(&json!(reply.fields))
    }

    fn print_market_entries(&mut self, response: &Value) -> Result<()> {
        let source = &response["source"];
        let mut lines = vec![
            format!(
                "Market catalog: {} · {} cached entries · offset {}",
                source["name"].as_str().unwrap_or_default(),
                response["total"],
                response["offset"]
            ),
            format!(
                "Source: {} · {}",
                source["id"].as_str().unwrap_or_default(),
                source["status"].as_str().unwrap_or_default()
            ),
        ];
        if let Some(commit) = source["source_commit"]
            .as_str()
            .filter(|value| !value.is_empty())
        {
            lines.push(format!("Git commit: {commit}"));
        }
        if let Some(hash) = source["content_sha256"]
            .as_str()
            .filter(|value| !value.is_empty())
        {
            lines.push(format!("Catalog SHA-256: {hash}"));
        }
        if let Some(error) = source["error"].as_str().filter(|value| !value.is_empty()) {
            lines.push(format!("Refresh error: {error}"));
        }
        for entry in response["items"].as_array().into_iter().flatten() {
            lines.push(format!(
                "{} · {} · {}\n  {}",
                entry["name"].as_str().unwrap_or_default(),
                entry["version"].as_str().unwrap_or_default(),
                entry["source_kind"].as_str().unwrap_or_default(),
                entry["description"].as_str().unwrap_or_default()
            ));
        }
        if let Some(offset) = response["next_offset"].as_u64() {
            lines.push(format!(
                "Next cache page: /markets show {} {offset}",
                source["id"].as_str().unwrap_or_default()
            ));
        }
        if source["next_cursor"]
            .as_str()
            .is_some_and(|cursor| !cursor.is_empty())
        {
            lines.push(format!(
                "Next remote page: /markets more {}",
                source["id"].as_str().unwrap_or_default()
            ));
        }
        if response["total"] == 0 {
            lines.push(format!(
                "Refresh an enabled source with /markets refresh {}",
                source["id"].as_str().unwrap_or_default()
            ));
        }
        self.screen.print(&display_text(&lines.join("\n")))?;
        Ok(())
    }

    pub(super) async fn markets_command(&mut self, args: &[String]) -> Result<()> {
        match args.first().map(String::as_str).unwrap_or("list") {
            "list"|"status"=>{
                let response=self.request("listMarkets",json!({})).await?;
                let sources=&response["markets"]["sources"];
                let mut lines=vec![format!("Markets: {} sources",sources.as_array().map_or(0,Vec::len))];
                for source in sources.as_array().into_iter().flatten() {
                    lines.push(format!("{} · {} · {} · {} entries\n  {}\n  {}",source["id"].as_str().unwrap_or_default(),source["name"].as_str().unwrap_or_default(),source["status"].as_str().unwrap_or_default(),source["entry_count"],source["kind"].as_str().unwrap_or_default(),source["location"].as_str().unwrap_or_default()));
                }
                self.screen.print(&display_text(&lines.join("\n")))?;
            }
            "add"=>{
                let kind=args.get(1).ok_or("Use /markets add <git|manifest|directory|mcp_registry> <name> <location> [manifest-path]. Quote names and paths containing spaces.")?;
                if !["git","manifest","directory","mcp_registry"].contains(&kind.as_str()) {return Err("Choose git, manifest, directory or mcp_registry.".into());}
                let name=args.get(2).ok_or("Supply a quoted market name.")?;
                let location=args.get(3).ok_or("Supply its URL or local directory.")?;
                let response=self.request("addMarket",json!({"kind":kind,"name":name,"location":location,"manifest_path":args.get(4)})).await?;
                self.screen.print(&display_text(&format!("Market added: {}\n{}",response["source"]["id"].as_str().unwrap_or_default(),response["source"]["name"].as_str().unwrap_or_default())))?;
            }
            "show"|"search"=>{
                let id=args.get(1).ok_or("Supply a source ID from /markets list.")?;
                let searching=args[0]=="search";
                let query=if searching {args.get(2).ok_or("Supply a quoted search query.")?.as_str()}else{""};
                let offset=args.get(if searching{3}else{2}).map(|value|value.parse::<usize>()).transpose()?.unwrap_or(0);
                let response=self.request("queryMarket",json!({"market_id":id,"query":query,"offset":offset,"limit":30})).await?;
                self.print_market_entries(&response)?;
            }
            "refresh"|"more"=>{
                if self.background.is_some() {return Err("A background operation is active. Stop it before refreshing another source.".into());}
                let id=args.get(1).ok_or("Supply a source ID from /markets list.")?;
                let cursor=if args[0]=="more" {
                    let response=self.request("listMarkets",json!({})).await?;
                    response["markets"]["sources"].as_array().and_then(|sources|sources.iter().find(|source|source["id"]==id.as_str())).and_then(|source|source["next_cursor"].as_str()).filter(|value|!value.is_empty()).ok_or("No next remote cursor is available.")?.to_owned()
                }else{String::new()};
                let pending=self.host.begin_market_refresh(&json!({"market_id":id,"cursor":cursor}))?;
                let host=self.host.clone();
                self.background_id=format!("market:{id}");
                self.background=Some(tokio::spawn(async move {host.complete_market_refresh(json!("terminal-market"),pending).await}));
                self.status=format!("Refreshing market {id} · /markets stop");
            }
            "stop"=>{
                if !self.background_id.starts_with("market:") {return Err("No marketplace refresh is active in this terminal.".into());}
                self.stop_context_operation().await?;
            }
            "enable"|"disable"|"remove"=>{
                let id=args.get(1).ok_or("Supply a source ID from /markets list.")?;
                let operation=args[0].as_str();
                let response=if operation=="remove" {self.request("removeMarket",json!({"market_id":id})).await?}else{self.request("setMarketEnabled",json!({"market_id":id,"enabled":operation=="enable"})).await?};
                let retained=response["markets"]["sources"].as_array().is_some_and(|sources|sources.iter().any(|source|source["id"]==id.as_str()));
                let state=if operation=="enable" {"enabled"}else if operation=="remove"&&!retained {"removed"}else{"disabled"};
                self.screen.print(&display_text(&format!("Market {state}: {id}")))?;
            }
            "help"=>self.screen.print("/markets list\n/markets add <git|manifest|directory|mcp_registry> <name> <location> [manifest-path]\n/markets show <id> [offset] · search <id> <query> [offset]\n/markets refresh <id> · more <id> · stop\n/markets enable <id> · disable <id> · remove <id>\nQuote names and paths containing spaces. Catalog reads do not execute installers or grant trust.")?,
            _=>return Err("Unknown market command. Use /markets help.".into()),
        }
        Ok(())
    }
}
