"""
pyAirtable exposes a command-line interface that allows you to interact with the API.
"""

import datetime
import functools
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

import click
from typing_extensions import ParamSpec, TypeVar

from pyairtable.api.api import Api
from pyairtable.api.base import Base
from pyairtable.models._base import AirtableModel
from pyairtable.orm.generate import ModelFileBuilder

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
P = ParamSpec("P")


@dataclass
class CliContext:
    access_token: str = ""
    base_id: str = ""
    click_context: Optional["click.Context"] = None

    @functools.cached_property
    def api(self) -> Api:
        return Api(self.access_token)

    @functools.cached_property
    def base(self) -> Base:
        return self.api.base(self.base_id)

    @property
    def click(self) -> click.Context:
        assert self.click_context is not None
        return self.click_context

    def default_subcommand(self, cmd: F) -> None:
        if not self.click.invoked_subcommand:
            self.click.invoke(cmd)


def needs_context(func: Callable[P, T]) -> Callable[P, T]:
    @functools.wraps(func)
    @click.pass_context
    def _wrapped(click_ctx: click.Context, /, *args: P.args, **kwargs: P.kwargs) -> T:
        obj = click_ctx.ensure_object(CliContext)
        obj.click_context = click_ctx
        return click_ctx.invoke(func, obj, *args, **kwargs)

    return _wrapped


# fmt: off
@click.group()
@click.option("-k", "--key", help="Your API key")
@click.option("-kf", "--key-file", type=click.Path(exists=True), help="File containing your API key")
@click.option("-ke", "--key-env", metavar="VAR", help="Env var containing your API key")
@needs_context
# fmt: on
def cli(
    ctx: CliContext,
    key: str = "",
    key_file: str = "",
    key_env: str = "",
) -> None:
    if not any([key, key_file, key_env]):
        try:
            key_file = os.environ["AIRTABLE_API_KEY_FILE"]
        except KeyError:
            try:
                key = os.environ["AIRTABLE_API_KEY"]
            except KeyError:
                raise click.UsageError("--key, --key-file, or --key-env required")

    if len([arg for arg in (key, key_file, key_env) if arg]) > 1:
        raise click.UsageError("only one of --key, --key-file, --key-env allowed")

    if key_file:
        with open(key_file) as inputf:
            key = inputf.read().strip()

    if key_env:
        key = os.environ[key_env]

    ctx.access_token = key


@cli.command()
@needs_context
def bases(ctx: CliContext) -> None:
    """
    Output a JSON list of available bases.
    """
    _dump(ctx.api._base_info().bases)


@cli.group(invoke_without_command=True)
@click.argument("base_id")
@needs_context
def base(ctx: CliContext, base_id: str) -> None:
    """
    Retrieve information about a base.
    """
    ctx.base_id = base_id
    ctx.default_subcommand(base_schema)


@base.command("schema")
@needs_context
def base_schema(ctx: CliContext) -> None:
    """
    Output a JSON representation of the base schema.
    """
    _dump(ctx.base.schema())


@base.command("orm")
@needs_context
@click.option("-t", "--table", "table_names", multiple=True)
def base_auto_orm(ctx: CliContext, table_names: List[str]) -> None:
    """
    Generate a module with ORM classes for the given base.
    """
    generator = ModelFileBuilder(ctx.base, table_names=table_names)
    print(str(generator))


class JSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, AirtableModel):
            return o._raw
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return super().default(o)


def _dump(obj: Any) -> None:
    json.dump(obj, cls=JSONEncoder, fp=sys.stdout)


if __name__ == "__main__":
    cli()
