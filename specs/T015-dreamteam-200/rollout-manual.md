# T015 — manual lossless rollout 2.0.0, раунд 2

Дата: 2026-10-16. Исполнитель: devops-r2-manual. Это свидетельства
ручного переноса, не заявление об успешной автоматической миграции.
T015 остаётся Doing до финального независимого review и CI итогового SHA.

## База, разрешения и воспроизводимость

- Согласованный и фактический starting HEAD:
  `8cb36e0249179c7e4183e4d556a282af3415cd55`; before/after одинаковы,
  свежий собственный worktree чист, выравнивание не требовалось.
- Проверенный лидом origin/main: `253ba49fa3fdb2055cc944577287c97c84b62aea`.
- Host devbox, один существующий сервер; новый сервер/ACP/CLI не запускался,
  активная команда не перезапускалась. Глобальные настройки не менялись.
- Пользователь разрешил full MANUAL meaningful transfer при известном initial
  rc2 Content conflict; generic seed ADD2 — допустимое ограничение ручного
  пути, но НЕ noop и НЕ разрешение unattended apply. T171 automatic AC10
  этим локальным решением не переписывается.
- `dt --version`: dreamteam2.0.0; прочитаны публичные help init/update.
  Штатный `dt init .venv/t015-render --defaults` с прежними public answers
  (ru/uv/project name/description/author/architect_model) отрендерил ровно28
  файлов. Исходники установленного CLI не читались; прежний DENY не повторялся
  и не обходился. Pending permission ID ранее не возвращён.
- `uv sync --locked` создал только собственную .venv (Python3.14.4),
  установил17 exact locked packages, скачав numpy2.5.2. Lock и исходные
  окружения не менялись. Offline предпочтителен, но пользователь разрешил
  штатную загрузку точных locked dependencies.

## A — полный inventory и semantic mapping до деактивации

28 ниже — фактический final output публичного init, не восстановленный
по догадке managed manifest. «Сохранён» означает существующий project content,
не замену приложения generic seed. Custom inventory приведён отдельно.

| № | Rendered path | Native/project mapping и действие |
| --- | --- | --- |
| 1 | `.copier-answers.yml` | Прежние public answers; после A review только truthful2.0.0 provenance; ручной путь явно задокументирован |
| 2 | `.gitignore` | Project ignores, включая `.worktrees/`, сохранены |
| 3 | `.opencode/agents/architect.md` | Все уникальные project reasoning/protocol/ADR правила сохранены; удалён только идентичный duplicate; deny-by-default и explicit question:deny |
| 4 | `.opencode/agents/backend.md` | Backend/data/persistence contract сохранён; question:deny |
| 5 | `.opencode/agents/designer.md` | UX/visual/accessibility contract сохранён; question:deny; внешний сервис не prerequisite |
| 6 | `.opencode/agents/devops.md` | Pipeline/recovery/shared-resource/no-secret contract сохранён; question:deny |
| 7 | `.opencode/agents/frontend.md` | UI/API contract сохранён; question:deny |
| 8 | `.opencode/agents/mobile.md` | Platform/API contract сохранён; question:deny |
| 9 | `.opencode/agents/reviewer.md` | Independent review contract сохранён; deny-by-default и question:deny |
| 10 | `.opencode/agents/tech-lead.md` | Полный ownership/exactbase/worktree/checkpoint/recovery contract сохранён; единственный question:allow |
| 11 | `.opencode/agents/tester.md` | Behavior/regression/integration contract сохранён; question:deny |
| 12 | `.opencode/ensemble.json` | mergeOnCleanup:false сохранён |
| 13 | `.opencode/team-roles.md` | Native autoload; полный decision loop, design brief→visual spec→target stack, controls и actual unfinished continuity |
| 14 | `AGENTS.md` | Полная существующая методика сохранена, actor names/pointers native; фактические canonical gates с Xvfb/guard |
| 15 | `BACKLOG.md` | Queue сохранена; только native actor name |
| 16 | `BOARD.md` | Только T015 status/evidence, Doing до итоговой приёмки |
| 17 | `CHANGELOG.md` | Только запись T015 Unreleased; без выпуска |
| 18 | `CONCEPT.md` | Immutable, byte-identical |
| 19 | `DECISIONS.md` | Исторические ADR без изменений, добавлена запись T015 manual path |
| 20 | `README.md` | Canonical native pointers и actual gates; продуктовый текст без изменений |
| 21 | `hooks/pre-push` | Только stderr diagnostic CLAUDE.md→AGENTS.md; ветвления/exit/bootstrap запрет push без изменений |
| 22 | `opencode.json` | Schema, pinned Ensemble0.18.0, default tech-lead, instructions сохранены; provider/model отсутствуют |
| 23 | `pyproject.toml` | Stack и lint/type/test policy byte-identical |
| 24 | `scripts/pytest-guard.sh` | Code/mutex/memory wrapper byte-identical |
| 25 | `specs/design-brief-template.md` | Native designer/teamroles pointers, весь brief сохранён |
| 26 | `specs/spec-template.md` | Только actor names; полный clarify/analyze protocol сохранён |
| 27 | `src/main.py` | Product code byte-identical; generic seed ADD не применяется |
| 28 | `tests/test_main.py` | Product tests byte-identical; generic seed ADD не применяется |

### Полный custom inventory вне этих28

- Legacy sources: `CLAUDE.md`, `.claude/agents/architect.md`,
  `.claude/team-roles.md`; их смысл перенесён в активные AGENTS/native roles/
  teamroles, а оригиналы сохранены privately. Архив сам по себе переносом
  поведения не считается.
- `.github/workflows/ci.yml`, `.python-version`, `uv.lock`, `lbs-liner.spec`,
  `examples/sample.cdr`: неизменные project/CI/data contracts.
- `scripts/__init__.py`, `scripts/make_sample.py`, `scripts/verify_output.py`:
  неизменные project tooling contracts.
- `src/lbs_liner/{__init__,cdr_read,cdr_write,convert,dialogs,geometry,gui,riff,settings,synthetic}.py`:
  всё приложение неизменно.
- `tests/{conftest,test_cdr_read,test_cdr_write,test_geometry,test_gui,test_riff,test_settings}.py`:
  тесты неизменны; test_main уже учтён в28.
- `specs/T015-dreamteam-200/rollout-preflight.md`: исходный r1 evidence сохранён
  как исторический partial checkpoint, initialrc2 не переименован в unsupported.
- Новые собственные T015 evidence files не являются managed template paths.
  Coordinator inventory не редактировался.

Ни tracked project, ни rendered28 не имеют отдельного command/rules directory.
Это проверенное отсутствие, а не отказ от переноса: рабочие команды uv/dt,
проверки, hook и mutex представлены активными инструкциями и действующим
tooling. Не вводятся выдуманные slash commands или обязательный Design MCP.

### Private originals: фактический count, не подгонка

До первого изменения tracked files создан новый root:
`~/.local/share/dreamteam/migration-20261016/lbs-liner-T015-r2-manual-85d0aa296e/`.
Все директории0700, файлы0600; старые архивы не перезаписывались.

Фактически22 originals: baseline19 (legacy3 + native roles9 + AGENTS,
answers, README, hook, opencode, ensemble, teamroles7), дополнительно
specs/spec-template, specs/design-brief-template, BACKLOG, потому что их
canonical references тоже меняются. `manifest.json` — дополнительный
служебный файл0600, не «23-й оригинал».

Для каждого файла выполнено byte comparison source→archive и SHA256;
22/22 совпали с исходным git base8cb36e0. Полный manifest приватный и содержит
paths, sizes, hashes, modes, base, root; raw originals не коммитятся.
Лид независимо проверил все22 hashes/bytes/modes до деактивации.
Semantic review отдельно от проверки архива — см. chronological result ниже.

## Активное поведение и continuity

- OpenCode автозагружает AGENTS, instructions дополнительно teamroles;
  native9 roles находятся в .opencode/agents. Runtime JSON/default-agent/
  mergeOnCleanup проверены stdlib JSON load, а не по одному описанию.
- Actual frontmatter assertions: modes primary/subagent; questions8deny1allow;
  у architect/reviewer wildcarddeny + только existing readonly/communication
  allowlist. Shell/edit/MCP им не выдавались. Это проверка файлов конфигурации,
  не заявление о live reload: текущая сессия остаётся на старом snapshot.
- Архитектор сохраняет context→tradeoffs→recommendation→openfork, файлы
  источники и ADR draft. Решает человек через leadquestion; пишет final ADR
  лид/человек. Специалистам вопросы — через team_message. Design brief остаётся
  visual specification, перевод в целевой стек — отдельный согласованный шаг.
- Реальная unfinished T015: r1 partial→8cb36e0 checkpoint→новый r2 author;
  ожидаем initial dryrun rc2 architect content conflict, не testfailure.
  Native payload указывает BOARD и r1/r2 evidence; shutdown terminal,
  новая итерация только от checkpoint с новым unique name.
- Один сервер/attach, dt recover exact member/lead-session/task после interruption,
  uncertainty reconciliation до повтора; exactly-once/универсальный recovery
  не обещаются. Это не новый recovery test и не рестарт active team.

## Неприкосновенные contracts и оставшиеся проверки

CorelDRAW X7+17–22, additive originals/new layer, shapely и bit0x08,
Windows unified GUI/exe, сознательный Linux Tcl/Tk limitation сохранены.
Пользовательские данные в репозиторий не добавлялись, sample синтетический.
CI Linux/Xvfb80 + Windows build/smoke неизменен; srv onboarding не подтверждён.
IDE этот project не открыт: IDE build недоступен, чужой calque project
для проверки не используется. Canonical CLI gates остаются обязательны.

## Chronological A/B/C — фактическое исполнение

### A: review до деактивации и provenance

1. При clean8cb36e0 созданы и byte-checked все22 private originals.
2. Получен полный public render28; reviewer переданы все28 mapping и custom
   inventory, substantive native payload, archive path/hash/size/mode manifest.
3. Лид независимо проверил22/22 bytes/hashes against gitbase8cb36e0,
   все файлы0600, каталоги0700 и manifest0600.
4. Новые native payload/controls внесены без удаления legacy/answersupdate;
   actual assertions подтвердили questions8deny1allow, modesprimary/subagent,
   readonly wildcarddeny+existingallowlist, JSON autoload/default/mergefalse.
5. Reviewer-r2-manual дал **A predeactivation PASS** по mapping/payload,
   архиву и controls. Он отдельно указал: exact AGENTS changedblocks не
   отобразились в его входящих сообщениях и должны быть прочитаны при C
   через доступный интегрированный checkpoint. Не заявляется, что он их
   уже прочитал. A — не финальный review/merge.
6. Только после этого удалены три active legacy sources и обновлены две
   provenance строки .copier-answers.yml. Значения _commit2.0.0 и _src_path
   **точно совпадают с фактическим штатным init output**, public answers
   сохранены. Source bundle не читался; это не подмена inputs для dry-run.
   Полный manual mapping/provenance записан в местном ADR T015.

### B: полный ordinary repeat, без фильтрации входов

После manual переноса выполнен `dt update --dry-run .` шесть раз с неизменными
inputs. Каждый раз **rc0**, полный вывод состоит из пустой строки и summary:

```text
dreamteam update --dry-run: 0 would change, 28 unchanged, 0 added, 0 removed, 0 conflicts.
```

Это весь actual plan: per-file diff отсутствует, а не скрыт. Никаких force,
apply, подмены answers между повторами, skip или фильтрации managed inputs
не было. SHA256 каждого existing tracked file before/after совпал; legacy
удаление произошло вручную ДО этих вызовов, не dry-run. Содержимое roles,
AGENTS, autoload/controls и все остальные tracked paths не менялось вызовами.

**Не путать наблюдения:** initial rc2 Content conflict зафиксирован r1 и
подтверждён r2 до ручного переноса. Ожидавшийся generic ADD2 в этих post-manual
полных повторах НЕ наблюдался. Утверждать «rc0ADD2 значит noop» нельзя:
в случае появления `src/main.py`/`tests/test_main.py` ADD2 это реальные записи
в product scope и known limitation, без unattended apply. Текущий actual
result0/28/0/0/0 не является доказательством automatic legacy migration или
переписанным T171 acceptance: provenance изменена вручную после A review.

### C: canonical gates и граница приёмки

Собственное окружение явно задано `VIRTUAL_ENV=$PWD/.venv`, `uv run --active`.
После deactivation/provenance выполнена цепочка без подавления exit codes:

```bash
uv run --active ruff check .
uv run --active ruff format --check .
uv run --active mypy src tests scripts
xvfb-run -a scripts/pytest-guard.sh --cov=src --cov-report=term-missing --cov-fail-under=80
```

- ruff: **All checks passed**.
- format: **35 files already formatted** (до удаления legacy было38).
- mypy: **no issues found in22 source files**.
- Xvfb+mutex full pytest: **55 passed**, **86.10% coverage**, threshold80,
  последний прогон1.22s. Не вводились новые suppressions или test weakening.
- IDE build вызван для собственного worktree и вернул **project not open**;
  единственный открытый проект calque не использовался.
- `git diff --check` выполнен; protected application/CI/stack/lock/pin/guard
  paths не менялись. Native role/control assertions выполняются отдельно от
  pytest; это не притворный runtime restart/reload test.

Финальный независимый C review полного diff (особенно AGENTS), GitHub CI
итогового SHA и repository acceptance остаются лиду. Run links здесь не
выдумываются: исполнитель не push/PR/merge. T015 остаётся Doing. Executive
main merge hold — отдельное ограничение, не красный тест. Исходный checkout
на migration/opencode не активировался, cleanup и server restart не делались.
