---
name: gog
description: Google Workspace CLI — Gmail, Calendar, Drive, Sheets, Docs, Contacts. Пиши и обновляй документацию в Google Docs и Sheets через командную строку.
homepage: https://gogcli.sh
metadata: {"clawdbot":{"emoji":"🗂️","requires":{"bins":["gog"]}}}
---

# gog — Google Workspace CLI

## Окружение (уже настроено на smain)

```bash
# Оба переменных уже в systemd env openclaw-gateway — вызывать gog можно без префиксов.
# Если вдруг нужно вручную:
export GOG_KEYRING_PASSWORD=openclaw
export GOG_ACCOUNT=bshevelev75@gmail.com
```

Авторизован аккаунт `bshevelev75@gmail.com` со всеми сервисами (gmail, calendar, drive, docs, sheets, contacts, tasks...).

### Shectory-ресурсы

| Ресурс | ID |
|---|---|
| Папка shectory (Drive) | `1_4Yk7kpSs8FTNxbP4w0V1o301Vqa6mRa` |
| Таблица Shectory Agents (Sheets) | `19t2-J9_EUGFNFu6PrFM72JGipc-THfOetjyER6EeGss` |

---

## Workflow: написать документацию в Google Docs

### Шаг 1 — создать документ из markdown

```bash
# Напиши контент в /tmp/doc.md, затем:
gog docs create "Название документа" \
  --file /tmp/doc.md \
  --parent 1_4Yk7kpSs8FTNxbP4w0V1o301Vqa6mRa \
  -j
# Вернёт docId — сохрани его!
```

### Шаг 2 — обновить существующий документ (замена)

```bash
gog docs write <docId> \
  --file /tmp/updated.md \
  --markdown \
  --replace
```

### Шаг 3 — дописать в конец документа

```bash
gog docs write <docId> \
  --file /tmp/appendix.md \
  --markdown \
  --append
```

### Читать документ обратно

```bash
gog docs cat <docId>                        # plain text
gog docs export <docId> --format md --out /tmp/out.md  # markdown
gog docs structure <docId>                  # структура с номерами параграфов
gog docs raw <docId> -j                     # raw JSON (для скриптов)
```

### Точечные правки

```bash
# Найти и заменить текст
gog docs find-replace <docId> "старый текст" "новый текст"

# Regex замена (sed-style)
gog docs sed <docId> "s/v1\.0/v2\.0/g"

# Вставить в начало документа
gog docs insert <docId> "## Обновлено: 2026-05-08\n\n" --index 1

# Удалить диапазон символов
gog docs delete --start 0 --end 100 <docId>

# Очистить весь документ
gog docs clear <docId>
```

---

## Sheets: обновлять таблицы-документацию

```bash
# Записать данные (через --values-json — единственный надёжный способ)
gog sheets update <sheetId> "Лист1!A1" \
  --values-json '[["Заголовок1","Заголовок2"],["строка1_1","строка1_2"]]' \
  --input USER_ENTERED

# Дописать строки
gog sheets append <sheetId> "Лист1!A1" \
  --values-json '[["новая строка", "данные"]]' \
  --insert INSERT_ROWS

# Прочитать диапазон
gog sheets get <sheetId> "Лист1!A1:D10" -p

# Очистить диапазон
gog sheets clear <sheetId> "Лист1!A2:Z100"

# Метаданные таблицы (список листов, sheetId для форматирования)
gog sheets metadata <sheetId> -j

# Форматировать заголовок
gog sheets format <sheetId> "Лист1!A1:Z1" \
  --format-json '{"textFormat":{"bold":true},"backgroundColor":{"red":0.1,"green":0.1,"blue":0.18},"wrapStrategy":"WRAP"}' \
  --format-fields 'textFormat,backgroundColor,wrapStrategy'
```

**Важно про Sheets:** Символ `|` разделяет ячейки внутри строки (в inline-синтаксисе), `,` разделяет строки. Но для всего сложного используй `--values-json` — надёжнее.

---

## Drive: файлы и папки

```bash
gog drive ls                               # корень Drive
gog drive ls <folderId>                    # содержимое папки
gog drive search "query"                   # поиск файлов
gog drive mkdir "Новая папка"              # создать папку
gog drive mkdir "Вложенная" --parent <id>  # в конкретную папку
gog drive move <fileId> --parent <folderId> -y  # переместить
gog drive rename <fileId> "Новое имя"     # переименовать
```

---

## Gmail

```bash
gog gmail search 'newer_than:7d is:unread' --max 20
gog gmail send \
  --to boris@example.com \
  --subject "Отчёт" \
  --body "Текст письма" \
  --html                          # HTML-тело (опционально)
```

---

## Calendar

```bash
gog calendar events primary \
  --from 2026-05-08T00:00:00Z \
  --to   2026-05-09T00:00:00Z
```

---

## Правила

- Всегда используй `--no-input` в автоматических скриптах.
- Перед отправкой email — спроси подтверждения у Бориса.
- Перед созданием событий в календаре — спроси подтверждения.
- Для документации: создавай файл в папке `shectory` (folderId выше) если не указано другое.
- `GOG_ACCOUNT` уже в env — `-a` можно не указывать.
