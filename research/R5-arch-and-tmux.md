# R5 — Extensible Plugin Architecture & tmux Integration (Raw Findings)

> **Archived first-pass research** — superseded by [`../knowledge/sources/`](../knowledge/sources/); folded into [`../knowledge/agent-eng/`](../knowledge/agent-eng/README.md) + [`../knowledge/principles/`](../knowledge/principles/README.md). See [`README.md`](README.md). Kept for provenance.


Research date: 2026-07-07. Source: codex live web-search (4 parallel runs), cross-checked.
Two independent topics below. Keep them separate.

---

# PART A — EXTENSIBLE PLUGIN ARCHITECTURE (Python)

Model the system as a pipeline:

```
Effect ABC -> parameter schema -> registry -> discovery -> renderer/theme injection
```

Pragmatic core recommendation: `Effect` ABC + Pydantic `params_model` + decorator
registry for in-repo effects + entry points for third-party effects + an explicit
`theme` argument passed into every render path (theme as dependency, not global).

## A.1 Decorator Registry (with collision policy + lazy loading)

```python
# smartcli/effects/registry.py
from __future__ import annotations
from dataclasses import dataclass
from importlib import import_module
from typing import Callable, TypeVar

T = TypeVar("T")

class RegistryError(Exception):
    pass

@dataclass(frozen=True)
class LazySpec:
    module: str
    attr: str

class EffectRegistry:
    def __init__(self) -> None:
        self._items: dict[str, type] = {}
        self._lazy: dict[str, LazySpec] = {}

    def register(self, name: str, *, replace: bool = False) -> Callable[[type[T]], type[T]]:
        def decorator(cls: type[T]) -> type[T]:
            if not replace and (name in self._items or name in self._lazy):
                raise RegistryError(f"effect name already registered: {name!r}")
            self._items[name] = cls
            self._lazy.pop(name, None)
            return cls
        return decorator

    def register_lazy(self, name: str, target: str, *, replace: bool = False) -> None:
        if not replace and (name in self._items or name in self._lazy):
            raise RegistryError(f"effect name already registered: {name!r}")
        module, _, attr = target.partition(":")
        if not module or not attr:
            raise ValueError("target must look like 'package.module:ClassName'")
        self._lazy[name] = LazySpec(module, attr)
        self._items.pop(name, None)

    def get(self, name: str) -> type:
        if name in self._items:
            return self._items[name]
        spec = self._lazy.get(name)
        if spec is None:
            raise KeyError(name)
        module = import_module(spec.module)
        cls = getattr(module, spec.attr)
        self._items[name] = cls
        del self._lazy[name]
        return cls

    def names(self) -> list[str]:
        return sorted(set(self._items) | set(self._lazy))

effects = EffectRegistry()
register_effect = effects.register
```

Usage:
```python
@register_effect("rainbow")
class RainbowEffect(Effect):
    name = "rainbow"
    description = "Cycle text through a rainbow palette."
    def render(self, text, *, theme): return text
```

Lazy built-ins (avoid importing every effect module at startup):
```python
effects.register_lazy("matrix", "smartcli.effects.matrix:MatrixEffect")
effects.register_lazy("sparkle", "smartcli.effects.sparkle:SparkleEffect")
```
Use `replace=True` only for intentional overrides (user plugin shadowing built-in).

## A.2 ABC Base Classes

```python
# smartcli/effects/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, ClassVar

class Effect(ABC):
    params_model: ClassVar[type | None] = None

    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    @abstractmethod
    def description(self) -> str: ...
    @abstractmethod
    def render(self, text: str, *, theme: Any) -> str: ...

    @classmethod
    def schema(cls) -> dict[str, Any]:
        model = cls.params_model
        if model is None:
            return {"type": "object", "properties": {}}
        if hasattr(model, "model_json_schema"):
            return model.model_json_schema()
        raise TypeError(f"{cls.__name__}.params_model does not expose schema")
```

For class-level required metadata use abstract classmethods:
```python
class Pattern(ABC):
    @classmethod
    @abstractmethod
    def plugin_name(cls) -> str: ...
    @abstractmethod
    def frame(self, t: float, width: int, height: int) -> str: ...
```

## A.3 Entry-Point / Plugin Discovery

Python 3.10+ selectable API:
```python
# smartcli/plugins.py
from importlib.metadata import entry_points
from smartcli.effects.base import Effect
from smartcli.effects.registry import effects

ENTRY_POINT_GROUP = "smartcli.effects"

def load_entry_point_effects() -> None:
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        cls = ep.load()
        if not issubclass(cls, Effect):
            raise TypeError(f"{ep.name} is not an Effect subclass")
        effects.register(ep.name)(cls)
```

Plugin package pyproject.toml:
```toml
[project.entry-points."smartcli.effects"]
glitch = "smartcli_glitch:GlitchEffect"
scanlines = "smartcli_glitch:ScanlineEffect"
```

Lazy entry-point loading (defer `.load()` until used, lower startup cost):
```python
class EntryPointRegistry:
    def __init__(self) -> None:
        self._eps = {ep.name: ep for ep in entry_points(group="smartcli.effects")}
        self._loaded: dict[str, type[Effect]] = {}
    def get(self, name: str) -> type[Effect]:
        if name not in self._loaded:
            self._loaded[name] = self._eps[name].load()
        return self._loaded[name]
```

Sources:
- https://docs.python.org/3/library/importlib.metadata.html
- https://packaging.python.org/en/latest/specifications/pyproject-toml/#entry-points
- https://packaging.python.org/specifications/entry-points/

### pluggy (pytest's plugin system)

```python
# smartcli/hookspecs.py
import pluggy
hookspec = pluggy.HookspecMarker("smartcli")
class SmartCLISpec:
    @hookspec
    def smartcli_register_effects(self, registry):
        """Register effects into the host registry."""

# third_party_plugin.py
import pluggy
from smartcli_glitch import GlitchEffect
hookimpl = pluggy.HookimplMarker("smartcli")
class GlitchPlugin:
    @hookimpl
    def smartcli_register_effects(self, registry):
        registry.register("glitch")(GlitchEffect)

# smartcli/plugin_manager.py
import pluggy
from smartcli.hookspecs import SmartCLISpec
pm = pluggy.PluginManager("smartcli")
pm.add_hookspecs(SmartCLISpec)
pm.register(GlitchPlugin())
pm.hook.smartcli_register_effects(registry=effects)
```
pytest structure: hook specs in `_pytest.hookspec`, plugins implement same-named
functions, `PytestPluginManager` loads built-ins, conftest.py, and entry-point plugins.
Sources: https://pluggy.readthedocs.io/ , https://docs.pytest.org/en/stable/how-to/writing_plugins.html ,
https://docs.pytest.org/en/stable/_modules/_pytest/hookspec.html

## A.4 Parameter Schemas

Prefer Pydantic when params come from CLI/config (validation + JSON Schema built in):
```python
from pydantic import BaseModel, Field
class RainbowParams(BaseModel):
    speed: float = Field(1.0, ge=0.1, le=10.0, description="Animation speed")
    saturation: float = Field(0.85, ge=0.0, le=1.0)
    direction: str = Field("forward", pattern="^(forward|reverse)$")

class RainbowEffect(Effect):
    params_model = RainbowParams
    name = "rainbow"; description = "Cycle text through a rainbow palette."
    def __init__(self, params: RainbowParams | None = None):
        self.params = params or RainbowParams()
    def render(self, text, *, theme): return text
```

Auto-generate help from schema:
```python
def effect_help(effect_cls: type[Effect]) -> str:
    schema = effect_cls.params_model.model_json_schema()
    lines = []
    for name, prop in schema.get("properties", {}).items():
        default = prop.get("default", "<required>")
        lines.append(f"--{name} ({prop.get('type','any')}, default={default}) {prop.get('description','')}")
    return "\n".join(lines)
```

Dataclass alternative (lighter, weaker validation):
```python
from dataclasses import dataclass, field, fields, MISSING
@dataclass(frozen=True)
class WaveParams:
    amplitude: int = field(default=4, metadata={"min":1,"max":20,"help":"Wave height"})
    frequency: float = field(default=1.0, metadata={"min":0.1,"max":10.0})
```

attrs (middle ground, validators/converters):
```python
import attrs
@attrs.define(frozen=True)
class SparkleParams:
    density: float = attrs.field(default=0.15,
        validator=attrs.validators.and_(attrs.validators.ge(0.0), attrs.validators.le(1.0)),
        metadata={"help":"Fraction of cells that sparkle"})
```

Comparison:
- dataclasses: stdlib, minimal, good for internal typed config, weak validation.
- attrs: ergonomic validators/converters, good middle ground, extra dep.
- pydantic: best for external user input, JSON Schema, CLI/config validation, heavier.

Sources: https://docs.python.org/3/library/dataclasses.html ,
https://pydantic.dev/docs/concepts/json_schema/ , https://www.attrs.org/en/stable/api.html

## A.5 Theme Injection

Treat colors as dependencies, not globals. Semantic names resolve late through the
active renderer/context.

Explicit theme argument (own palette):
```python
from dataclasses import dataclass
@dataclass(frozen=True)
class Palette:
    primary: str = "cyan"; accent: str = "magenta"
    warning: str = "yellow"; error: str = "red"

class PulseEffect(Effect):
    name = "pulse"; description = "Pulse text with the accent color."
    def render(self, text, *, theme: Palette):
        return f"[{theme.accent}]{text}[/]"
```

Rich Theme:
```python
from rich.console import Console
from rich.theme import Theme
theme = Theme({"effect.primary":"cyan","effect.accent":"bold magenta","effect.error":"bold red"})
console = Console(theme=theme)
console.print("[effect.accent]Hello[/]")
# temporary override:
with console.use_theme(Theme({"effect.accent":"green"})):
    console.print("[effect.accent]temporary green[/]")
```
APIs: `Theme(styles, inherit=True)`, `Console(theme=)`, `console.get_style(name, default=)`,
`console.use_theme(theme, inherit=True)` (context mgr), `console.push_theme()/pop_theme()`,
`Style.parse("bold red on black")`, style composition `base + Style(underline=True)`,
`Segment.apply_style(segments, style, post_style)`.
Sources: https://rich.readthedocs.io/en/stable/reference/theme.html ,
https://rich.readthedocs.io/en/stable/style.html

Textual (CSS/design-system injection): widgets define `DEFAULT_CSS`, reactive state.

## A.6 Rich Renderable Protocol (low-level rendering)

Two protocols in `rich.console`:
```python
@runtime_checkable
class RichCast(Protocol):
    def __rich__(self) -> Union["ConsoleRenderable","RichCast",str]: ...
@runtime_checkable
class ConsoleRenderable(Protocol):
    def __rich_console__(self, console: "Console", options: "ConsoleOptions") -> "RenderResult": ...

RenderableType = Union[ConsoleRenderable, RichCast, str]
RenderResult = Iterable[Union[RenderableType, Segment]]
```
- `RichCast.__rich__()`: lightweight conversion, returns another renderable/str.
- `ConsoleRenderable.__rich_console__()`: full hook, yields str / renderables / raw `Segment`.
- `Segment(text: str, style: Style | None = None, control=None)`: lowest render unit.
- `Measurement(minimum: int, maximum: int)` returned by `__rich_measure__(console, options)`
  when layout needs width (tables etc).

Full custom renderable example:
```python
from dataclasses import dataclass
from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.segment import Segment
from rich.style import Style

@dataclass
class SparkBar:
    value: float
    width: int = 20
    def __rich__(self) -> str:
        return f"[bold]SparkBar({self.value:.0%})[/]"
    def __rich_measure__(self, console, options) -> Measurement:
        return Measurement(self.width, self.width)
    def __rich_console__(self, console, options) -> RenderResult:
        filled = round(max(0.0, min(1.0, self.value)) * self.width)
        ok = console.get_style("bar.complete", default="green")
        rest = console.get_style("bar.remaining", default="dim")
        yield Segment("#" * filled, ok)
        yield Segment("." * (self.width - filled), rest)
        yield Segment(f" {self.value:.0%}", Style(bold=True))
```
Sources: https://rich.readthedocs.io/en/stable/protocol.html ,
https://rich.readthedocs.io/en/stable/reference/segment.html ,
https://rich.readthedocs.io/en/stable/reference/measure.html ,
https://github.com/Textualize/rich/blob/master/rich/console.py

## A.7 Textual Widget Extensibility

```python
from rich.segment import Segment
from rich.style import Style
from textual.app import App, ComposeResult, RenderResult
from textual.message import Message
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Label

class MeterChanged(Message):
    def __init__(self, value: int) -> None:
        super().__init__(); self.value = value

class Meter(Widget):
    DEFAULT_CSS = """
    Meter { height: 1; background: $surface; }
    """
    value = reactive(0, repaint=True)
    def compose(self) -> ComposeResult:
        yield Label("", id="caption")
    def watch_value(self, old: int, new: int) -> None:
        self.query_one("#caption", Label).update(f"{new}%")
        self.post_message(MeterChanged(new))
    def render(self) -> RenderResult:
        return f"[bold]Meter[/] {self.value}%"
    def render_line(self, y: int) -> Strip:
        width = self.size.width
        filled = round(width * self.value / 100)
        return Strip([Segment("#"*filled, Style(color="green")),
                      Segment("."*(width-filled), Style(color="grey50"))], width)
```
Key signatures:
- `compose(self) -> ComposeResult`
- `render(self) -> RenderResult` (simple content API)
- `render_line(self, y: int) -> Strip` (low-level per-row draw API)
- `mount(self, *widgets, before=None, after=None) -> AwaitMount`
- `post_message(self, message) -> bool`
- `reactive(default, *, layout=False, repaint=True, init=True, always_update=False,
   recompose=False, bindings=False, toggle_class=None)`
- watcher method naming convention: `watch_<attrname>(self, old, new)`

Sources: https://textual.textualize.io/guide/widgets/ ,
https://textual.textualize.io/api/widget/ , https://textual.textualize.io/api/reactive/ ,
https://textual.textualize.io/guide/events/

## A.8 Textual App / Screen / TCSS + design tokens

```python
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Header, Footer, Label, Button

class Dashboard(Screen):
    DEFAULT_CSS = """
    Dashboard { background: $background; }
    #panel { background: $surface; color: $foreground; border: tall $primary; padding: 1 2; }
    Button.primary { background: $primary; color: $text-primary; }
    """
    def compose(self) -> ComposeResult:
        yield Header(); yield Label("Effects dashboard", id="panel")
        yield Button("Run", classes="primary"); yield Footer()

class EffectsApp(App[None]):
    CSS = "Screen { align: center middle; }"
    SCREENS = {"dashboard": Dashboard()}
    def on_mount(self) -> None:
        self.register_theme(Theme(name="effects-dark",
            primary="#7dd3fc", secondary="#c084fc", accent="#f59e0b",
            foreground="#e5e7eb", background="#101418", surface="#18202a",
            panel="#202a36", dark=True))
        self.theme = "effects-dark"
        self.push_screen("dashboard")
```
Design tokens: `$primary`, `$secondary`, `$foreground`, `$background`, `$surface`,
`$panel`, `$boost`, plus generated variants `$text-primary`, `$primary-muted`, etc.
Sources: https://textual.textualize.io/guide/design/ ,
https://textual.textualize.io/guide/screens/ , https://textual.textualize.io/api/app/

## A.9 Animation Timing

Rich Live (drive at N fps):
```python
from time import sleep
from rich.live import Live
fps = 30
with Live("", refresh_per_second=fps, auto_refresh=False) as live:
    for frame in range(300):
        live.update(f"[cyan]frame {frame}[/]", refresh=True)
        sleep(1 / fps)
```
`Live(renderable=None, *, console=None, screen=False, auto_refresh=True,
refresh_per_second=4, transient=False, redirect_stdout=True, redirect_stderr=True,
vertical_overflow="ellipsis", get_renderable=None)`

Textual timer loop:
```python
class Spinner(Widget):
    frame = reactive(0)
    def on_mount(self) -> None:
        self.set_interval(1/30, self.tick, name="spinner-fps")
    def tick(self) -> None:
        self.frame += 1
    def render(self) -> str:
        glyphs = "..."  # spinner glyph set
        return glyphs[self.frame % len(glyphs)]
```
Timer API (on MessagePump, so widgets/apps/screens all have it):
- `set_timer(delay, callback=None, *, name=None, pause=False) -> Timer`
- `set_interval(interval, callback=None, *, name=None, repeat=0, pause=False) -> Timer`
Sources: https://rich.readthedocs.io/en/stable/live.html ,
https://textual.textualize.io/guide/animation/

## A.10 Other lib extensibility patterns

Click/Typer command groups:
```python
import click
@click.group()
def cli(): pass
@click.command()
def sparkle(): click.echo("sparkle")
cli.add_command(sparkle)

# entry-point loaded commands:
from importlib.metadata import entry_points
def load_commands():
    for ep in entry_points(group="smartcli.commands"):
        cli.add_command(ep.load(), name=ep.name)

# Typer composition:
import typer
app = typer.Typer(); effects_app = typer.Typer()
app.add_typer(effects_app, name="effects")
```
```toml
[project.entry-points."smartcli.commands"]
sparkle = "smartcli_sparkle.cli:sparkle"
```
Sources: https://click.palletsprojects.com/en/stable/entry-points/ ,
https://typer.tiangolo.com/tutorial/subcommands/add-typer/

---

# PART B — TMUX INTEGRATION

Dev machine has NO tmux (Windows). All integration scripts must be POSIX sh that
detect + degrade gracefully.

## B.1 Version requirement

`display-popup` requires **tmux >= 3.2** (3.2 added per-client overlay popups).
Sources: https://man7.org/linux/man-pages/man1/tmux.1.html ,
https://github.com/tmux/tmux/issues/2592

## B.2 display-popup

Syntax:
```sh
tmux display-popup [-BCEkN] [-b border-lines] [-c target-client] [-d start-directory] \
  [-e VARIABLE=value] [-h height] [-s style] [-S border-style] [-t target-pane] \
  [-T title] [-w width] [-x position] [-y position] [shell-command [argument ...]]
```
Key flags / examples:
```sh
tmux display-popup -E 'command'                 # close popup when command exits
tmux display-popup -EE 'command'                # close only if command exits successfully
tmux display-popup -w 80% -h 80% -E 'command'   # width/height as percentages
tmux display-popup -x C -y C -w 80% -h 80% -E 'cmd'  # centered (C = center)
tmux display-popup -d "$PWD" -E 'command'       # start in directory
tmux display-popup -T 'animation' -E 'command'  # title
tmux display-popup -b rounded -S 'fg=cyan,bg=default' -s 'bg=black,fg=white' -E 'cmd'
tmux display-popup -B -E 'command'              # no border
```
Terminal-art examples:
```sh
tmux display-popup -w 80% -h 80% -x C -y C -T 'animation' -E 'bash -lc "python3 ./animate.py"'
tmux display-popup -w 100 -h 30 -x C -y C -T 'clock' -EE 'bash -lc "tty-clock -c"'
tmux display-popup -d "$PWD" -w 80% -h 80% -E 'bash -lc "cmatrix"'
```
Gotchas:
- Without `-E`, popup stays open after command exits. `-EE` leaves it open on failure (debug).
- Width/height default to half terminal size if omitted.
- Inside an existing popup, most placement flags ignored; only `-b -B -C -E -EE -k -N -s -S`.

## B.3 Panes & layouts

```sh
tmux split-window [-bdefhIkPvZ] [-c dir] [-e VAR=val] [-l size] [-p pct] [-t target] [cmd]
tmux split-window -h                 # split L/R, new pane right
tmux split-window -v                 # split top/bottom, new pane below
tmux split-window -h -p 30           # new pane = 30% width
tmux split-window -v -l 20           # new pane = 20 rows
tmux split-window -h -l 30%          # size may be percentage
tmux split-window -h -c "$PWD" 'bash -lc "python3 ./animate.py"'
```
Layouts: `even-horizontal even-vertical main-horizontal main-vertical tiled`
```sh
tmux select-layout tiled
```
Targeting/resizing:
```sh
tmux select-pane -t sess:0.1   (or -L -R -U -D)
tmux resize-pane -t sess:0.1 -L 10   (-R -U -D)
tmux resize-pane -t sess:0.1 -x 80 -y 24    # absolute
tmux resize-pane -t sess:0.1 -x 50%         # percentage
tmux resize-pane -Z -t sess:0.1             # toggle zoom
```
Detached session + full layout:
```sh
tmux new-session -d -s art -n main -c "$PWD" 'bash'
tmux split-window -t art:0.0 -h -p 35 -c "$PWD" 'bash -lc "python3 ./animate.py"'
tmux split-window -t art:0.0 -v -p 50 -c "$PWD" 'bash -lc "top"'
tmux select-layout -t art:0 tiled
tmux attach-session -t art
```
One-shot chained layout:
```sh
tmux new-session -d -s agents -n control -c "$PWD" 'bash' \; \
  split-window -t agents:0.0 -h -p 50 -c "$PWD" 'bash' \; \
  split-window -t agents:0.1 -v -p 50 -c "$PWD" 'bash' \; \
  select-layout -t agents:0 tiled \; \
  select-pane -t agents:0.0
```
`new-session -d -s name` = detached; `-n` names first window; `-c` sets start dir.

## B.4 Run animation in a pane / lifecycle

```sh
tmux split-window -h -p 40 -c "$PWD" 'bash -lc "python3 ./animate.py"'
tmux new-session -d -s art -n anim -c "$PWD" 'bash -lc "python3 ./animate.py"'; tmux attach -t art
tmux split-window -h -k -c "$PWD" 'bash -lc "python3 ./animate.py"'   # -k keep exited pane visible
tmux respawn-pane -t art:0.0                    # rerun original cmd if pane inactive
tmux respawn-pane -k -t art:0.0 'bash -lc "python3 ./animate.py"'  # kill + replace
tmux kill-pane -t art:0.0
```

## B.5 capture-pane / send-keys (agent control)

```sh
tmux capture-pane [-aepPqCJMN] [-b buf] [-E end] [-S start] [-t target]
tmux capture-pane -p -t sess:0.1              # print visible pane to stdout
tmux capture-pane -p -S -200 -t sess:0.1      # last 200 scrollback lines + visible
tmux capture-pane -p -S - -t sess:0.1         # from start of history
tmux capture-pane -p -e -t sess:0.1           # include ANSI color/escape attrs
tmux capture-pane -p -J -S -200 -t sess:0.1   # join wrapped lines
tmux capture-pane -p -a -t sess:0.1           # capture alternate screen
```
```sh
tmux send-keys -t sess:0.1 'ls -la' Enter     # type command + run
tmux send-keys -t sess:0.1 C-c                # Ctrl-C (key name recognized)
tmux send-keys -l -t sess:0.1 'literal C-c'   # -l = literal text, disable key lookup
```
Agent-control loop:
```sh
tmux new-session -d -s agents -n work -c "$PWD" 'bash'
tmux send-keys -t agents:0.0 'npm test' Enter
sleep 2
tmux capture-pane -p -S -200 -t agents:0.0
tmux send-keys -t agents:0.0 C-c
```
Gotcha: `send-keys 'C-c'` (no `-l`) sends Ctrl-C; use `-l` for literal.

## B.6 Truecolor / 24-bit inside tmux

Recommended .tmux.conf:
```tmux
set -g default-terminal "tmux-256color"
set -as terminal-features ",*:RGB"
```
Older-compatible fallback:
```tmux
set -g default-terminal "tmux-256color"
set -as terminal-overrides ",*:Tc"
```
Per-terminal features: `,xterm-kitty:RGB` `,alacritty:RGB` `,wezterm:RGB` `,foot*:RGB` `,gnome*:RGB`
Verify:
```sh
tmux info | grep -E 'RGB|Tc|colors'
printf '\033[38;2;255;0;0mTRUECOLOR\033[0m\n'
```
Why colors look wrong: tmux must know the OUTER terminal supports RGB, else it maps to
256/16-color. tmux 3.2+ uses `terminal-features`; any version can use `terminal-overrides`.
Outside tmux `$TERM` = real terminal (xterm-kitty/wezterm/alacritty). Inside tmux
`$TERM` should be `tmux-256color`.
Passthrough (images/OSC/DCS):
```tmux
set -g allow-passthrough on    # only when pane visible
set -g allow-passthrough all   # even when invisible
tmux set-option -p -t art:0.0 allow-passthrough on   # per-pane
```
Note: passthrough does NOT make unsupported image protocols work; outer terminal must support them.
Sources: https://github.com/tmux/tmux/wiki/FAQ#how-do-i-use-rgb-colour ,
https://man7.org/linux/man-pages/man1/tmux.1.html

## B.7 Alt-screen behavior

```tmux
set -g alternate-screen on   (or off)
```
Full-screen apps (vim/less/top/htop/TUIs) use smcup/rmcup: enter alt screen, draw,
restore previous pane contents on exit.
```sh
tmux capture-pane -p -t sess:0.0        # normal visible screen
tmux capture-pane -p -a -t sess:0.0     # alternate screen (while app running)
tmux capture-pane -p -a -q -t sess:0.0  # -q quiet, no error if no alt screen
tmux send-keys -t sess:0.0 C-l          # clear visible terminal in pane
tmux clear-history -t sess:0.0          # clear tmux scrollback
```
Gotcha: `capture-pane -a` uses alt screen and history is NOT accessible there.

---

# PART B (cont) — POSIX SH GUARDS (dev machine has no tmux)

## B.8 Detection functions (POSIX sh, no bashisms)

```sh
has_tmux() { command -v tmux >/dev/null 2>&1; }

inside_tmux() {
    [ -n "${TMUX-}" ] && return 0     # $TMUX is the authoritative signal
    case "${TERM-}" in
        tmux*|screen*) return 0 ;;
        *) return 1 ;;
    esac
}

tmux_version() {                      # prints e.g. "3.4" from "tmux 3.4"
    has_tmux || return 1
    tmux -V 2>/dev/null | awk '{ print $2 }'
}

tmux_version_ge() {                   # usage: tmux_version_ge 3 2
    need_major=$1; need_minor=$2
    ver=$(tmux_version) || return 1
    major=${ver%%.*}
    rest=${ver#*.}
    minor=${rest%%[!0123456789]*}     # strip "3a" -> "3"
    [ -n "$major" ] || return 1
    [ -n "$minor" ] || minor=0
    [ "$major" -gt "$need_major" ] && return 0
    [ "$major" -eq "$need_major" ] && [ "$minor" -ge "$need_minor" ] && return 0
    return 1
}

tmux_popup_available() { has_tmux && inside_tmux && tmux_version_ge 3 2; }
```

## B.9 Graceful guard (popup or inline fallback)

```sh
run_popup_or_inline() {
    title=$1; cmd=$2                  # cmd is a shell command string; keep it trusted/static
    if tmux_popup_available; then
        tmux display-popup -E -w 80% -h 70% -T "$title" "$cmd"
    else
        sh -c "$cmd"                  # fallback: run inline in current terminal
    fi
}
```

## B.10 Terminal capability detection

```sh
stdout_is_tty()       { [ -t 1 ]; }
no_color_requested()  { [ -n "${NO_COLOR-}" ]; }         # https://no-color.org/
truecolor_supported() { case "${COLORTERM-}" in truecolor|24bit) return 0;; *) return 1;; esac; }
color_count()         { if command -v tput >/dev/null 2>&1 && [ -n "${TERM-}" ]; then
                            tput colors 2>/dev/null || printf '%s\n' 0
                        else printf '%s\n' 0; fi; }
color_supported() {
    stdout_is_tty || return 1
    no_color_requested && return 1
    truecolor_supported && return 0
    colors=$(color_count); [ "$colors" -ge 8 ] 2>/dev/null
}
animation_supported() {
    stdout_is_tty || return 1
    [ "${TERM-}" = dumb ] && return 1
    return 0
}
```

## B.11 POSIX sh gotchas (avoid these bashisms)

| Bashism (avoid)            | POSIX replacement                          |
|----------------------------|--------------------------------------------|
| `[[ "$x" == foo ]]`        | `[ "$x" = foo ]`                            |
| `arr=(one two)`            | `set -- one two`                           |
| `echo -e "a\nb"`           | `printf '%s\n' "a" "b"`                     |
| `function name { }`        | `name() { }`                               |
| `source ./file`            | `. ./file`                                 |
| `cmd &>log`                | `cmd >log 2>&1`                            |
| `for ((i=0;i<3;i++))`      | `while [ "$i" -lt 3 ]; do i=$((i+1)); done` |
| `${var:0:3}`               | use `cut`/`sed`/expr or pattern expansion  |
| `which prog`               | `command -v prog`                          |
| backticks `` `cmd` ``      | `$(cmd)`                                   |
| process subst `<(...)`     | avoid (temp file / pipe)                   |
| `local`                    | not POSIX; avoid                           |

Always quote vars: `[ -n "$var" ]`. Use `=` not `==` in `[ ]`.

Sources: https://pubs.opengroup.org/onlinepubs/009604499/utilities/xcu_chap02.html ,
https://www.shellcheck.net/wiki/SC2039 , https://no-color.org/ ,
https://man.openbsd.org/tmux.1
