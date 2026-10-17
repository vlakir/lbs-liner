# T015 — preflight исполнителя devops-r1 (частичный результат)

Дата: 2026-10-16. Это свидетельства и предварительное сопоставление,
**не приёмка миграции и не разрешение деактивировать legacy**.

## База и границы

- Согласованный и фактический starting HEAD:
  `7435b86c6f9003a852bbcd61da436a901d861a27`.
- `origin/main`, проверенный лидом: `253ba49fa3fdb2055cc944577287c97c84b62aea`.
- Собственный свежий worktree devops-r1 перед работой чист;
  выравнивание HEAD не выполнялось. Host: devbox.
- Scope: методика, native роли/инструкции/команды/контроли и T015-журнал.
  Исходники, тесты приложения, CI, стек/lock, CONCEPT, глобальные настройки,
  установленный и выпущенный CLI не изменялись.

## Фактический CLI preflight

`dt --version`: `dreamteam 2.0.0`; `dt --help` и `dt update --help`
прочитаны. Первый обычный `dt update --dry-run .` завершился с **rc 2**:

```text
ERROR: Content conflict: .opencode/agents/architect.md. No files changed.
```

Вывод захвачен в RAM, без сохранения raw settings/diffs. Категория —
**content conflict**, не unsupported. Второй диагностический вызов до
правок подтвердил ту же одну строку/rc. Никаких `--force`, apply,
подмены answers, фильтрации входов или исправления CLI не было.
Полный план ADD/UPDATE/DELETE CLI не выдал; отсутствие такого плана
не означает noop. Ожидаемые в полном плане `src/main.py` и
`tests/test_main.py` ADD2 нельзя считать noop или скрывать: приложение
вне scope и требует отдельного рассмотрения полного плана.

### Permission blocker

- Tool: `functions.grep` (readonly).
- Arguments: pattern `Content conflict|unsupported|legacy`, include `*.py`,
  path `/home/vlakir/.local/share/uv/tools/dreamteam-cli/lib/python3.14/site-packages/dreamteam`.
- Result: `The user rejected permission to use this specific tool call.`
- Pending permission ID: **NOT RETURNED**.
- Повтор/обход отклонённого чтения и доступ к тому же target другим
  инструментом не выполнялись. Лид уведомлён.

## Доступный project inventory и предварительный mapping

Это inventory файлов текущего репозитория, **не заявка на полноту всех
28 managed+custom шаблонных файлов**. В проекте не найден отдельный
tracked manifest с этими 28 позициями: `.copier-answers.yml` содержит
старую provenance 1.7.0, а не список файлов. `git ls-files` позволяет
установить project paths, но не определить отсутствующие managed paths.
Полный inventory поэтому пока не доказан.

| Project source | Native destination / статус |
| --- | --- |
| `CLAUDE.md` | `AGENTS.md`: методика сохранена; legacy ещё на месте |
| `.claude/agents/architect.md` | `.opencode/agents/architect.md`: контекст → варианты → рекомендация → развилка, ADR и read-only уже присутствуют; native содержит повтор preserved payload; причина CLI conflict не установлена |
| `.claude/team-roles.md` | `.opencode/team-roles.md`: автозагрузка через `opencode.json.instructions` есть; значимую петлю «предложил → человек решил → ADR» необходимо явно сохранить в active payload, не только архивом |
| `.copier-answers.yml` | Пока без изменения: нельзя выдавать новую provenance до review |
| `.opencode/agents/{tech-lead,architect,designer,frontend,mobile,backend,tester,reviewer,devops}.md` | Все девять native ролей tracked; architect/reviewer deny-by-default; проверка всех writer permission controls и explicit question deny ещё не завершена |
| `opencode.json` | Native runtime, pinned Ensemble0.18.0, default tech-lead, autoload team-roles; provider/model не задаются |
| `.opencode/ensemble.json` | `mergeOnCleanup:false`; явная интеграция, не auto merge |
| `hooks/pre-push` | Есть legacy ссылка на CLAUDE; поведение не изменено; обход hook не выполнялся |
| `scripts/pytest-guard.sh` | Сохранить mutex для полного coverage; не заменять голым pytest |
| `specs/{spec-template,design-brief-template}.md` | Существующие методические шаблоны; lossless review ещё требуется |
| `BOARD.md`, `BACKLOG.md`, `CHANGELOG.md`, `README.md`, `DECISIONS.md`, `CONCEPT.md` | Durable canon; T015 должен остаться Doing до всех AC; CONCEPT immutable |
| `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock`, `.python-version`, `lbs-liner.spec` | Контекст ограничений, не файлы реализации T015 |

Project `.claude/` имеет два tracked файла (архитектор и team-roles),
плюс корневой `CLAUDE.md`. Отсутствующие в этом inventory commands/rules/
controls не объявлены ненужными: полнота их переноса ещё не проверена.

## Неприкосновенные project contracts

- CDR X7+17–22, patch входного файла, исходное содержимое плюс новый слой;
  shapely side voting и порядок подпутей 0x08.
- Windows unified exe/GUI; Linux Tcl/Tk limitation — сознательное решение,
  не повод для побочного исправления.
- Чувствительные пользовательские файлы не коммитить, тесты синтетические.
- GitHub CI: `ruff check .`, `ruff format --check .`,
  `mypy src tests scripts`; Xvfb pytest с coverage ≥80%; Windows build/smoke.
- Локальный полный прогон — через guard и с Xvfb для GUI.
  В репозитории нет `scripts/srv_gates.py`/Forgejo workflow; лид подтвердил
  единственный configured remote GitHub. Подтверждения srv onboarding нет;
  самовольно вводить иной CI нельзя.

## Незавершённость и следующий безопасный шаг

Сначала снять blocker согласованным оператором, установить реальный полный
inventory и план CLI. Затем byte-identical private originals с каталогами
0700/файлами0600 и независимый review mapping **до** legacy deactivation
или provenance. На момент этого checkpoint private originals ещё не
созданы; их проверка не заявляется. Условия manual lossless переноса не
считаются выполненными одним лишь rc2 content conflict.

Поведенческие изменения, финальный повтор dry-run, фактические гейты,
PR/review/CI и приёмка остаются открыты. Checkpoint не закрывает T015.
