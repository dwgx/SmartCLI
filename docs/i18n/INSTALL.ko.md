<!-- Language: [English](../../INSTALL.md) | [简体中文](INSTALL.zh-Hans.md) | [繁體中文](INSTALL.zh-Hant.md) | [日本語](INSTALL.ja.md) | 한국어 -->

# SmartCLI 설치

SmartCLI는 하나의 교체 가능한 PTY + `pyte` 코어 위에 올라간 세 개의 Agent Skill(`cmd-art`, `drive-tui`, `tui-ui`)입니다. 설치 방법은 "폴더를 그냥 넣기"부터 일반적인 pip 설치까지 세 가지가 있습니다. 파일을 어떤 방식으로 받았는지에 맞는 방법을 고르세요.

## 요약 — 설정 없이 그냥 넣기

릴리스를 압축 해제한 뒤 저장소 전체(또는 스킬 폴더 하나만)를 AI의 스킬 디렉터리에 넣으세요. 처음 사용할 때 스스로 설정을 마칩니다.

- **`cmd-art`** 와 **`tui-ui`** 는 순수 Python 표준 라이브러리만 쓰며 완전히 자체 완결형입니다. 디스크에 존재하는 순간부터 동작하고, 설치하거나 연결할 것이 전혀 없습니다.
- **`drive-tui`** 는 `smartcli_core` 패키지와 `pyte` 라이브러리가 필요합니다. `skills/drive-tui/_vendor/` 안에 `smartcli_core` 사본을 번들로 함께 제공하므로, `drive-tui` 폴더만 단독으로 있어도 코어를 자동으로 찾습니다. 코어를 찾는 순서는 다음과 같습니다: `$SMARTCLI_ROOT` → `smartcli_core/` 를 포함한 상위 폴더 → 번들된 `_vendor/` → pip으로 설치된 사본.

모든 연결이 제대로 됐는지 확인하세요:

```bash
python skills/drive-tui/scripts/tui.py doctor
```

`smartcli_core` 를 어디에서 찾아왔는지, 그리고 런타임 의존성이 갖춰져 있는지를 출력하며, 빠진 것이 있으면 정확한 설치 명령까지 알려줍니다.

## 세 가지 시나리오

### 1. 저장소 전체 (권장)

저장소를 아무 곳에나 클론하거나 압축 해제하세요. 세 스킬 모두 그 자리에서 동작하며, `drive-tui` 는 저장소 루트까지 거슬러 올라가 `smartcli_core` 를 찾습니다.

```bash
git clone https://github.com/dwgx/SmartCLI
# or: unzip the release
python skills/drive-tui/scripts/tui.py doctor
```

### 2. 스킬 폴더 하나만 단독으로 넣기

스킬 폴더 하나(예: `skills/drive-tui/`)만 AI의 스킬 디렉터리에 복사하세요. `cmd-art` 와 `tui-ui` 는 그 외에 필요한 것이 없습니다. `drive-tui` 는 `smartcli_core` 를 `_vendor/` 에 지니고 다니므로, 그 하위 폴더만 온전히 유지하면 여전히 동작합니다:

```bash
python <dropped-in>/drive-tui/scripts/tui.py doctor
# smartcli_core: .../drive-tui/_vendor
```

### 3. Claude 플러그인

저장소에는 `.claude-plugin/plugin.json` 과 `.claude-plugin/marketplace.json` 이 포함되어 있어, 세 스킬을 모두 묶은 플러그인으로 설치됩니다:

```
/plugin marketplace add dwgx/SmartCLI
/plugin install smartcli@smartcli
```

### 4. pip (공유 코어를 라이브러리로)

`smartcli_core` 를 일반적인 임포트 가능한 라이브러리로 쓰려면:

```bash
pip install smartcli-toolkit   # import stays: from smartcli_core import PtySession
```

## 의존성

| 패키지 | 필요한 곳 | 자동? |
|---|---|---|
| `pyte` | `drive-tui` 코어 (필수 의존성) | `doctor` 가 알려줌; 요청 시 설치 |
| `pywinpty` | **Windows** 에서만 `drive-tui` | `doctor` 가 알려줌; 요청 시 설치 |
| `pyfiglet`, `Pillow`, `wcwidth` | 선택적 편의 기능 — 없어도 모두 무리 없이 동작함 | 절대 필수 아님 |

`drive-tui` 는 몰래 무언가를 설치하는 일이 절대 없습니다(설치는 네트워크 작업이므로). `pyte`/`pywinpty` 가 빠져 있으면 정확한 명령을 출력합니다. 이를 대신 설치하도록 허용하려면 명시적으로 옵트인하세요:

```bash
python skills/drive-tui/scripts/tui.py --install-deps start --cmd python
# or: set SMARTCLI_AUTO_INSTALL=1
```

또는 모든 것을 미리 설치할 수도 있습니다:

```bash
python -m pip install -r requirements.txt              # required
python -m pip install -r requirements-optional.txt     # optional extras
```

## 벤더링된 코어를 동기화 상태로 유지하기

`skills/drive-tui/_vendor/` 안의 `smartcli_core` 사본은 도구 하나와 테스트 하나를 통해 정본인 최상위 `smartcli_core/` 와 바이트 단위로 동일하게 유지됩니다:

```bash
python tools/sync_vendor.py          # refresh the vendored copy
python tools/sync_vendor.py --check  # exit 1 if it has drifted (CI/gate)
python tests/test_vendor_sync.py     # the regression lock
```

`smartcli_core/` 를 수정했다면, 커밋하기 전에 `sync_vendor.py` 를 실행하세요.
