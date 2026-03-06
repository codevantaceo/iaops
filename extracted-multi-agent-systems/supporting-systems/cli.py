import json
import os
from pathlib import Path

import click

from .engine import Engine


@click.group()
def main():
    pass


@main.command()
@click.option(
    "--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False)
)
@click.option(
    "--project", "project_root", required=True, type=click.Path(exists=True, file_okay=False)
)
@click.option("--mode", "mode", required=False, type=str, default=None)
def run(config_path: str, project_root: str, mode: str | None):
    engine = Engine.from_config(Path(config_path), Path(project_root), mode=mode)
    result = engine.run()
    click.echo(json.dumps(result, indent=2, sort_keys=True))


@main.command()
@click.option(
    "--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False)
)
@click.option(
    "--project", "project_root", required=True, type=click.Path(exists=True, file_okay=False)
)
def plan(config_path: str, project_root: str):
    engine = Engine.from_config(Path(config_path), Path(project_root), mode="plan")
    result = engine.run()
    click.echo(json.dumps(result, indent=2, sort_keys=True))


@main.command()
@click.option(
    "--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False)
)
@click.option(
    "--project", "project_root", required=True, type=click.Path(exists=True, file_okay=False)
)
def verify(config_path: str, project_root: str):
    engine = Engine.from_config(Path(config_path), Path(project_root), mode="verify")
    result = engine.run()
    click.echo(json.dumps(result, indent=2, sort_keys=True))


@main.command()
@click.option(
    "--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False)
)
@click.option(
    "--project", "project_root", required=True, type=click.Path(exists=True, file_okay=False)
)
def seal(config_path: str, project_root: str):
    engine = Engine.from_config(Path(config_path), Path(project_root), mode="seal")
    result = engine.run()
    click.echo(json.dumps(result, indent=2, sort_keys=True))


@main.command()
@click.option("--state-dir", "state_dir", required=False, type=click.Path())
def clean(state_dir: str | None):
    sd = Path(state_dir or ".indestructibleautoops")
    if sd.exists():
        for root, dirs, files in os.walk(sd, topdown=False):
            for name in files:
                Path(root, name).unlink(missing_ok=True)
            for name in dirs:
                Path(root, name).rmdir()
        sd.rmdir()
    click.echo(json.dumps({"cleaned": str(sd)}, indent=2, sort_keys=True))
