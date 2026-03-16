mod backend;
mod config;
mod panel_snapshot;
mod session;
mod surfaces;

use backend::{mode_label, probe as probe_backend, run as run_backend};
use config::Config;
use std::env;
use std::path::PathBuf;

#[derive(Debug, Default)]
struct Cli {
    config_path: Option<PathBuf>,
    once: bool,
    emit_json: bool,
    probe: bool,
    ticks: Option<u32>,
}

fn parse_args() -> Result<Cli, String> {
    let mut cli = Cli::default();
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--config" => {
                let value = args
                    .next()
                    .ok_or_else(|| "--config requires a path".to_string())?;
                cli.config_path = Some(PathBuf::from(value));
            }
            "--once" => cli.once = true,
            "--emit-json" => cli.emit_json = true,
            "--probe" => cli.probe = true,
            "--ticks" => {
                let value = args
                    .next()
                    .ok_or_else(|| "--ticks requires an integer".to_string())?;
                cli.ticks = Some(
                    value
                        .parse::<u32>()
                        .map_err(|_| "--ticks must be an integer".to_string())?,
                );
            }
            "--help" | "-h" => {
                print_help();
                std::process::exit(0);
            }
            unknown => return Err(format!("unsupported argument: {unknown}")),
        }
    }
    Ok(cli)
}

fn print_help() {
    println!("AIOS shell compositor service");
    println!("  --config <path>   Load compositor config");
    println!("  --once            Run one lifecycle tick and exit");
    println!("  --ticks <n>       Run n lifecycle ticks and exit");
    println!("  --probe           Probe backend readiness and emit a structured summary");
    println!("  --emit-json       Emit a final JSON lifecycle summary");
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = parse_args()
        .map_err(|message| std::io::Error::new(std::io::ErrorKind::InvalidInput, message))?;
    let config = Config::load(cli.config_path.as_deref())?;
    let tick_target = if cli.once { Some(1) } else { cli.ticks };

    println!(
        "starting shell compositor service_id={} runtime={} desktop_host={} smithay_mode={}",
        config.service_id,
        config.session_backend,
        config.desktop_host,
        mode_label(&config)
    );

    let session = if cli.probe {
        probe_backend(&config)?
    } else {
        run_backend(&config, tick_target)?
    };

    if cli.emit_json {
        println!("{}", session.json_summary());
    } else if cli.probe {
        println!(
            "probed shell compositor service_id={} lifecycle_state={} smithay_status={} renderer_status={} outputs={} connected={} primary_output={}",
            session.service_id,
            session.lifecycle_state,
            session.smithay_status,
            session.renderer_status,
            session.output_count,
            session.connected_output_count,
            session.primary_output_name.as_deref().unwrap_or("-"),
        );
    } else {
        println!(
            "stopped shell compositor service_id={} ticks={} lifecycle_state={} smithay_status={} surface_count={}",
            session.service_id,
            session.ticks,
            session.lifecycle_state,
            session.smithay_status,
            session.surfaces.len()
        );
    }

    Ok(())
}
