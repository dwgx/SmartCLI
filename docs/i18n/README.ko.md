<!-- Language: [English](../../README.md) | [简体中文](README.zh-Hans.md) | [繁體中文](README.zh-Hant.md) | [日本語](README.ja.md) | 한국어 -->

# SmartCLI

*다른 언어로 읽기: [English](../../README.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · **한국어***

**터미널을 조작하고, 인식하고, 렌더링하기 위한 로컬 Python 툴킷 — 플러그인 방식의 PTY + `pyte` 코어 위에 얹은 3개의 에이전트 스킬.**

[![PyPI](https://img.shields.io/pypi/v/smartcli-toolkit?color=orange)](https://pypi.org/project/smartcli-toolkit/)
[![Python](https://img.shields.io/pypi/pyversions/smartcli-toolkit?color=blue)](https://pypi.org/project/smartcli-toolkit/)
[![CI](https://github.com/dwgx/SmartCLI/actions/workflows/ci.yml/badge.svg)](https://github.com/dwgx/SmartCLI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/pypi/l/smartcli-toolkit?color=green)](../../LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/smartcli-toolkit?color=blueviolet)](https://pypi.org/project/smartcli-toolkit/)
[![Skills: 3](https://img.shields.io/badge/skills-3-purple)](#기능)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#설치)

## 개요와 목적

SmartCLI는 에이전트와 사람이 함께 수행하는 터미널 작업을 위한 워크스페이스입니다: 대화형 터미널 프로그램을 **조작하고**, 화면이 실제로 무엇을 보여 주는지 **인식하고**, 시각 요소와 레이아웃을 다시 **렌더링**하는 작업이죠. 이 툴킷은 하나의 공유 가능한 플러그인 방식 PTY 백엔드와 `pyte` 화면 모델 위에 구축되었습니다 — 스크린샷/비전 방식 대신 이 방식을 택한 이유는, 단일한 구조적 화면 모델이 인식(화면 읽기)과 렌더링(화면 그리기)을 모두 뒷받침하도록 하기 위해서입니다. PTY 계층은 의도적으로 tmux에 묶여 있지 **않습니다**: 로컬 개발은 Windows에서 ConPTY(`pywinpty`)를 통해 이뤄지며, 대상 프로그램은 다른 환경의 POSIX pty나 tmux 위에서 실행될 수 있습니다. 이 코어 위에 3개의 스킬이 놓이며, 각각은 체크아웃한 위치에서 그대로 실행하는 독립형 도구입니다.

로컬 개발은 Windows 11, Python 3.14.6, `pyte` + `pywinpty` / ConPTY 환경에서 이뤄지며, CI 는 Windows + Linux + macOS 매트릭스에서 검증합니다. 실제 `tmux` 는 아직 검증되지 않았으므로, 스크린샷 리포트는 실제 tmux 캡처가 아니라 정직하게 `pyte-simulation`으로 표기됩니다.

## 실제 TUI 조작하기

SmartCLI가 **lazygit** — 실제 전체 화면 curses 앱 — 을 인식 → 조작 → 확인
루프를 통해 조작하는 모습입니다: `pyte` 셀 그리드를 읽고, 방향키로 이동하며,
커밋의 diff 를 열고, 브랜치를 하이라이트합니다. 스크립트로 흉내 낸 것이 아니라
Linux 컨테이너에서 실제 프로그램을 직접 조작해 캡처했습니다. pexpect 같은
바이트 스트림 매처는 "어느 행이 하이라이트되어 있는지"를 인식할 수 없지만,
화면 모델은 할 수 있습니다.

<p align="center">
  <img src="../../showcase/drive-lazygit.gif" alt="SmartCLI가 lazygit 을 조작하는 모습" width="700">
</p>

> 정직한 범위 안내: CI 는 Windows + Linux + macOS 매트릭스를 실행합니다. POSIX pty
> 백엔드(spawn/read/drive/resize/좀비 없는 종료)는 CI 에서 Linux 와 macOS 모두에서
> 검증됩니다. 대화형 DECCKM/SS3 방향키 프로브는 CI 러너에서는 건너뛰며 여전히
> 실제 머신에서의 실행이 필요합니다. 실제 tmux 는 아직 검증되지 않았습니다 —
> [`skills/drive-tui/references/LIMITATIONS.md`](../../skills/drive-tui/references/LIMITATIONS.md)를
> 참고하세요.

## 스크린샷

`fx` 엔진으로 렌더링한 `cmd-art` 이펙트의 작은 갤러리입니다. 각 이펙트는 `python -m fx play <name>`으로 재현할 수 있습니다([빠른 시작](#빠른-시작) 참고).

| | | |
|:---:|:---:|:---:|
| ![donut](../../showcase/donut.png) | ![fire](../../showcase/fire.png) | ![plasma](../../showcase/plasma.png) |
| **donut** | **fire** | **plasma** |
| ![rain](../../showcase/rain.png) | ![starfield](../../showcase/starfield.png) | ![tunnel](../../showcase/tunnel.png) |
| **rain** | **starfield** | **tunnel** |

## 설치

**기본 방식 — PyPI에서 설치:**

```bash
pip install smartcli-toolkit
```

> **배포 이름 vs 임포트 이름:** PyPI 배포 이름은 `smartcli-toolkit`이지만
> (`smartcli` / `smart-cli`라는 이름은 이미 선점되었거나 차단되어 있습니다),
> 임포트 가능한 패키지는 `smartcli_core`입니다. 따라서 `pip install smartcli-toolkit`
> 이후에도 여전히 `from smartcli_core import PtySession`이라고 작성합니다.

**대안 — 소스 체크아웃에서 전체 개발 환경 재현:**

```bash
git clone https://github.com/dwgx/SmartCLI SmartCLI
cd SmartCLI
python -m pip install -r requirements.txt
```

`requirements.txt`은 필수 런타임 의존성 두 가지만 설치합니다: `pyte`(모든 환경)와
`pywinpty`(Windows 전용 — 마커가 POSIX에서는 이를 건너뛰며, POSIX는 표준 라이브러리의 `pty`
백엔드를 사용합니다). 체크아웃한 위치에서 `pip install .`을 실행하면 동일한 임포트 가능한
`smartcli_core` 패키지가 설치됩니다.

솔직한 범위 안내: `pip install smartcli-toolkit`은 깔끔하고 임포트 가능한 `smartcli_core`
패키지와 그 필수 의존성을 설치합니다. 세 개의 스킬을 옮겨 놓지는 **않습니다** — 이들은
빠른 시작에서 보여 주듯 각자의 진입점(`python -m fx`, `python -m ui`,
`skills/drive-tui/scripts/tui.py`)을 통해 제자리에서 실행됩니다. 이는 의도된 설계이며,
자세한 내용은 [`pyproject.toml`](../../pyproject.toml) 상단의 안내를 참고하세요.

**선택적 추가 기능** (실제 FIGlet 폰트, 래스터 이미지, 신뢰할 수 있는 셀 너비 — 없을 경우
모두 표준 라이브러리 폴백으로 자연스럽게 다운그레이드됩니다):

```bash
python -m pip install -r requirements-optional.txt
# or, from the checkout, via pyproject extras:
pip install ".[all]"        # pyfiglet + Pillow + wcwidth
pip install ".[art]"        # pyfiglet only
pip install ".[image]"      # Pillow only  (also: the PNG screenshot harness needs it)
pip install ".[width]"      # wcwidth only
```

**Windows 참고:** 박스 드로잉 문자와 CJK 글리프가 깨끗하게 인코딩되도록, 스킬을 실행하기 전에
UTF-8 출력을 설정하세요(CLI가 stdout을 자동으로 재구성하기도 하지만, 안전을 위해 설정해 두세요):

```powershell
set PYTHONIOENCODING=utf-8
```

개발 머신(Windows 11, CPython 3.14.6)에서 검증한 의존성 버전: `pyte` 0.8.2,
`pywinpty` 3.0.5, `pyfiglet` 1.0.4, `Pillow` 12.2.0, `wcwidth` 0.8.1.

## 빠른 시작

### cmd-art — 터미널 비주얼 이펙트

```bash
cd skills/cmd-art
python -m fx list                          # list all 19 effects
python -m fx play donut --seconds 5        # play one effect (bounded)
python -m fx gallery                       # one frame of each effect
python -m fx show --seq "donut:fire:3,plasma::3"
```

### tui-ui — 셀 단위로 정확한 터미널 UI

```bash
cd skills/tui-ui
python -m ui widgets                       # list all 15 widgets
python -m ui gallery --width 100 --height 30
python -m ui demo table --width 80 --height 12 --theme dashboard
```

### drive-tui — 대화형 프로그램 인식 및 조작

지속 세션 CLI (셸 호출을 넘어 상태가 유지됩니다):

```bash
python skills/drive-tui/scripts/tui.py start --cmd "python" --cols 80 --rows 24
python skills/drive-tui/scripts/tui.py wait-regex --id <SID> ">>> " --timeout-ms 15000
python skills/drive-tui/scripts/tui.py send-line --id <SID> "print(6*7)"
python skills/drive-tui/scripts/tui.py snapshot --id <SID>
python skills/drive-tui/scripts/tui.py close --id <SID>
```

### 라이브러리로 사용하기

공유 코어는 직접 임포트할 수 있습니다:

```python
import sys
from smartcli_core import PtySession

s = PtySession()
s.start([sys.executable, "-q"])
s.wait_for(r">>> ")            # readiness sync, never a blind sleep
print(s.snapshot().to_text())  # pyte-backed structured screen
s.close()
```

전체 명령 레퍼런스, 스크린샷/AGENTCLI 하네스, 회귀 테스트 스위트는
**[`README-USAGE.md`](../../README-USAGE.md)**를 참고하세요.

## 기능

**`cmd-art`** (`skills/cmd-art`) — "살아 있는 템플릿" 방식의 이펙트 엔진: `Effect` ABC +
`@register` 데코레이터 + 자동 발견으로 구성됩니다. **18개 이펙트**(donut, fire, plasma, rain,
starfield, tunnel, text3d, cube, sphere, boids, life, fireworks, sparkle, decrypt,
gradient_text, banner_scroll, image2ascii, typewriter)를 **8개 테마**(mono, fire,
ocean, synthwave, viridis, pastel, matrix-green, rainbow)에 걸쳐 제공합니다. 이펙트는
순수한 프레임 생성자이며, `play`는 기본적으로 시간이 제한되어 있고 언제나 터미널을 원래대로 복원합니다.

**`tui-ui`** (`skills/tui-ui`) — 웹처럼 동작하는 터미널 레이아웃 엔진으로, tmux에 안전한
ANSI 프레임을 내보냅니다(SGR 컬러 런 + 줄바꿈만 사용하며, 커서 이동이나 대체 화면은 없습니다). **15개
위젯**(badge, banner, braille_chart, card, gradient_rule, kv, meter, panel,
progress, radial_glow, rule, slider_track, table, tabs, tree)을 실제 **엔진** 위에서 제공합니다:
`field.py`(셰이더 컴포지터), `raster.py`(서브 셀 단위 half/quad/braille 픽셀),
`box_junction.py`(에지 대수 기반 박스 결합), `color_model.py`(정직한 트루컬러 → 256 →
16 → mono 다운그레이드). CJK/이모지/ZWJ에 대해 표시 셀 단위로 정확하므로 열이 절대 어긋나지 않습니다.

**`drive-tui`** (`skills/drive-tui`) — 대화형 터미널 프로그램(REPL, 메뉴, 페이저, y/N
프롬프트, 마법사)을 PTY를 통해 조작합니다. 무작정 sleep을 넣는 대신
인식 → 판단 → 실행 → 대기 → 확인 루프를 따릅니다. 얇은 CLI
(`scripts/tui.py`)가 지속형 분리 세션과 일회성 `run` 모드를 제공하며,
화면을 `classify()`하고 `drive()`하는 임포트 가능한 패턴 라이브러리로 **8개 레시피**(repl, menu_select, pager, search_filter,
confirm, form, progress, wizard)를 함께 제공합니다.

**공유 코어** (`smartcli_core`) — 플러그인 방식 PTY 백엔드 + `pyte` 화면 모델 +
시맨틱 스냅샷 + 준비 상태 동기화(`pty_backend / screen_model / snapshot / readiness /
session`). 세 스킬 모두의 기반이 되는 재사용 가능하고 임포트 가능한 토대입니다.

**지식 그래프** (`knowledge/`) — 정확한 렌더링 공식, ANSI 시퀀스, 실측 상수를 담은
122개 노트의 위키링크 그래프로, 각 노트에는 출처와 상호 링크가 달려 있습니다. [`knowledge/INDEX.md`](../../knowledge/INDEX.md)를 참고하세요.

## 프로젝트 구조

```text
SmartCLI/
  smartcli_core/           shared PTY + pyte engine (importable package)
  skills/cmd-art/          fx effect package and CLI (19 effects, 8 themes)
  skills/drive-tui/        TUI pattern library and PTY driver CLI (8 recipes)
  skills/tui-ui/           terminal UI layout engine and widgets (15 widgets)
  tools/screenshot/        pyte -> PNG smoke-test harness
  tools/agentcli/          agent-CLI control validation harness
  knowledge/               122-note knowledge graph (see knowledge/INDEX.md)
  showcase/                rendered effect PNGs (see Screenshots)
  tests/                   direct script-style regressions
  research/                archived first-pass research notes
```

## 문서

- **[`README-USAGE.md`](../../README-USAGE.md)** — 전체 사용법 치트시트: 모든 스킬,
  스크린샷 및 AGENTCLI 하네스, 회귀 테스트 명령.
- **[`knowledge/INDEX.md`](../../knowledge/INDEX.md)** — 122개 노트의 지식 그래프.
- **[`AGENTCLI-VALIDATION.md`](../../AGENTCLI-VALIDATION.md)** — 에이전트-CLI 제어 테스트 매트릭스.
- **[`CHANGELOG.md`](../../CHANGELOG.md)** — 릴리스 기록.

## 라이선스

MIT — [LICENSE](../../LICENSE)를 참고하세요.
