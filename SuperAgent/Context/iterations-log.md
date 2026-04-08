# Лог итераций проекта

---
## Итерация #1
**Дата**: 2026-03-30
**Запрос**: Портирование admin API-модулей из rdpproxy v1 в rdpproxy-v2.

### Действие 1.1
**Описание**: Добавлены файлы в `src/services/admin/routes/`: servers, templates, sessions, admin_users, ad_groups, stats, settings. Импорты обновлены под v2 shared libs.

---
## Итерация #2
**Дата**: 2026-03-30
**Запрос**: Фаза 2 — Portal + Admin сервисы: app.py, main.py, middleware, routes, templates.

### Действие 2.1
Созданы Portal service: `app.py` (FastAPI factory), `main.py`, `dependencies.py`, middleware (security_headers, correlation_id, real_ip), routes (auth, servers, health).

### Действие 2.2
Созданы Admin service: `app.py`, `main.py`, `dependencies.py`, middleware (audit), routes (auth, cluster, services_mgmt).

### Действие 2.3
Скопированы HTML-шаблоны из v1 (login.html → portal, admin_*.html → admin).

### Действие 2.4
Исправлен `TemplateResponse` API (Starlette 1.0.0): `TemplateResponse(request, name, context)`.

### Действие 2.5
Docker compose build + up → portal (8001) и admin (9090) работают, health check OK.

---
## Итерация #3
**Дата**: 2026-03-30
**Запрос**: Фаза 3 — RDP Relay сервис.

### Действие 3.1
Созданы: `tcp_utils.py` (keepalive, abort), `plugins/base.py` (RdpPlugin, SessionContext), `plugins/registry.py` (PluginRegistry), `plugins/mcs_patch.py` (McsPatchPlugin), `plugins/session_monitor.py` (SessionMonitorPlugin).

### Действие 3.2
Создан `relay.py`: bidirectional pipe с хуками on_client_packet / on_backend_packet.

### Действие 3.3
Создан `handler.py`: полный lifecycle — PP v2 → X.224 → TLS → CredSSP → relay + tracking.

### Действие 3.4
Создан `main.py`: asyncio TCP server с graceful shutdown.

### Действие 3.5
Добавлена `build_session_factory()` в `db/engine.py`.

### Действие 3.6
Docker build + up → RDP Relay слушает на :8002, оба плагина зарегистрированы.

---
## Итерация #4
**Дата**: 2026-03-30
**Запрос**: Фаза 4 — HAProxy конфигурация + nftables.

### Действие 4.1
Создана HAProxy конфигурация (`deploy/haproxy/haproxy.cfg`):
- ft_mux (:8443) — L4 мультиплексер по первому байту (0x03=RDP, 0x16=TLS)
- bk_rdp → rdp-relay:8002 с send-proxy-v2
- ft_portal_https (127.0.0.1:8444) — TLS терминация → bk_portal (portal:8001)
- ft_admin (:9090) → bk_admin (admin:9090) с X-Forwarded-For

### Действие 4.2
Исправлен `req.peek` → `req.payload` (HAProxy 2.9), путь сертификата `/usr/local/etc/haproxy/certs/rdp.pem`.

### Действие 4.3
Создан `deploy/scripts/gen-dev-cert.sh` — генерация self-signed сертификата для dev.

### Действие 4.4
Созданы nftables правила (`deploy/nftables/rules.nft`): 8443 public, 9090 LAN-only.

### Действие 4.5
HAProxy запущен: `Loading success`. Portal health через HTTPS OK, admin через LAN IP OK.

---
## Итерация #5
**Дата**: 2026-03-30
**Запрос**: Фаза 5 — Metrics collector.

### Действие 5.1
Создан `services/metrics/collector.py`: psutil snapshot (CPU, RAM, disk), Redis publish (latest, series, heartbeat), PostgreSQL upsert (cluster_nodes).

### Действие 5.2
Создан `services/metrics/main.py`: asyncio event loop с graceful shutdown.

### Действие 5.3
Docker build + up → метрики пишутся в Redis и PostgreSQL. `cluster_nodes` содержит node-1.

---
## Итерация #6
**Дата**: 2026-03-30
**Запрос**: Фаза 6 — Стабилизация.

### Действие 6.1
Обновлён `docker-compose.yml`: healthchecks для portal и admin, HAProxy ждёт healthy перед стартом.

### Действие 6.2
Создан `deploy/scripts/pg-backup.sh` — pg_dump → gzip с ротацией.

### Действие 6.3
Создан `README.md` с архитектурой, инструкциями, plugin system, backup, firewall.

### Действие 6.4
Все 7 контейнеров запущены и работают: postgres (healthy), redis (healthy), portal (healthy), admin (healthy), rdp-relay, metrics, haproxy.

---
## Итерация #7
**Дата**: 2026-03-30
**Запрос**: Полностью переписать контекстную документацию для быстрого онбординга AI-агентов.

### Действие 7.1
Переписан `SuperAgent/project-brief.md` в расширенном формате:
- цели проекта, перенос v1 -> v2;
- реализованные и новые требования;
- ключевые сценарии, ограничения и эксплуатационные принципы.

### Действие 7.2
Переписан `SuperAgent/tech-structure.md`:
- актуальный стек, сервисная топология, сеть, безопасность;
- git/операционные правила, roadmap HA;
- пошаговый технический онбординг AI-агента.

### Действие 7.3
Переписан `SuperAgent/Context/project-architecture.md`:
- детальная структура модулей и ответственности;
- потоки данных (portal/admin/relay/metrics);
- точки расширения и known pitfalls для разработки.

---
## Итерация #8
**Дата**: 2026-03-30
**Запрос**: После сетевого обрыва клиент уже отключен, но сессия остается активной.

### Действие 8.1
Добавлена диагностическая утилита `src/libs/common/agent_debug.py` для записи NDJSON-событий в runtime debug-log `/opt/rdpproxy-v2/.cursor/debug-81a07f.log` (без секретов).

### Действие 8.2
Добавлена временная инструментализация в `src/services/rdp_relay/tcp_utils.py`:
- лог наличия socket при `configure_tcp_keepalive`;
- лог успешного применения keepalive;
- лог ошибки применения keepalive.

### Действие 8.3
Добавлена временная инструментализация в `src/services/rdp_relay/relay.py`:
- лог старта `relay_bidirectional` в режиме ожидания двух ног;
- лог `timeout`-серий в `_pipe` (каждые 30 таймаутов);
- лог завершения каждой ноги (`direction`, `reason`, `transferred`).

### Действие 8.4
Добавлена временная инструментализация в `src/services/rdp_relay/handler.py`:
- лог возврата из relay в handler;
- лог вызова `tracker.finish(..., status="closed")`;
- лог вызова `tracker.finish(..., status="error")`.

### Действие 8.5
Проверка линтера для измененных файлов выполнена, ошибок не найдено.

### Действие 8.6
После первого прогона debug-файл не появился в workspace (воспроизведение было без читаемого runtime-трейса).
Для трассировки из контейнера добавлен volume в `docker-compose.yml`:
- `rdp-relay`: `./.cursor:/opt/rdpproxy-v2/.cursor`
Это позволяет писать в требуемый debug-файл напрямую из контейнера.

### Действие 8.7
Выявлена причина отсутствия логов после `recreate`: контейнер `rdp-relay` работал на старом образе без свежей инструментализации.
Выполнена пересборка и перезапуск сервиса:
```bash
docker compose up -d --build rdp-relay
```

### Действие 8.8
Подготовка к чистому прогону: попытка удалить `/opt/rdpproxy-v2/.cursor/debug-81a07f.log` показала, что файл отсутствует (чистое состояние для следующего воспроизведения).

### Действие 8.9
Получены runtime-доказательства из `/opt/rdpproxy-v2/.cursor/debug-81a07f.log`:
- keepalive применился успешно;
- `client->backend` завершился с `reason=eof`;
- `backend->client` ушел в длительный `timeout`-loop;
- возврата из relay в handler не произошло.
Вывод: зависание связано с ожиданием завершения обеих ног relay.

### Действие 8.10
Внесен целевой фикс в `src/services/rdp_relay/relay.py`:
- вместо `asyncio.gather(...)` добавлен запуск двух задач и `asyncio.wait(..., return_when=FIRST_COMPLETED)`;
- после завершения любой ноги принудительно закрываются оба writer (`abort_writer`);
- затем выполняется `gather(*tasks)` для корректного сбора результатов и финализации.

### Действие 8.11
Добавлен runtime лог `first relay leg completed` для post-fix проверки.

### Действие 8.12
Проверен линтер для `relay.py`: ошибок нет.

### Действие 8.13
Пересобран и перезапущен сервис `rdp-relay` для применения фикса:
```bash
docker compose up -d --build rdp-relay
```

### Действие 8.14
Перед post-fix прогоном очищен debug-лог:
- удален файл `/opt/rdpproxy-v2/.cursor/debug-81a07f.log`.

---
## Итерация #9
**Дата**: 2026-03-30
**Запрос**: Удалить временную instrumentation после подтверждения фикса.

### Действие 9.1
Удалена временная runtime-инструментация из:
- `src/services/rdp_relay/tcp_utils.py`
- `src/services/rdp_relay/relay.py`
- `src/services/rdp_relay/handler.py`

### Действие 9.2
Удален временный helper-файл `src/libs/common/agent_debug.py`.

### Действие 9.3
Удален временный volume для debug-логов из `docker-compose.yml`:
- `./.cursor:/opt/rdpproxy-v2/.cursor`

### Действие 9.4
Проверка линтера по измененным файлам: ошибок нет.

### Действие 9.5
Пересобран и перезапущен `rdp-relay` после удаления instrumentation:
```bash
docker compose up -d --build rdp-relay
```

---
## Итерация #10
**Дата**: 2026-03-30
**Запрос**: Загрузить фоновое изображение страницы входа ADC и добавить его в стайлгайд.

### Действие 10.1
Скачано изображение фона входа по URL:
`https://rd.dc319.ru:4433/logon/LogonPoint/receiver/images/common/ReceiverFullScreenBackground.jpg`

Сохранено в проект:
- `assets/images/ReceiverFullScreenBackground.jpg`

### Действие 10.2
Обновлен `styleguide.md`:
- в разделе палитры и фонов указан локальный путь `assets/images/ReceiverFullScreenBackground.jpg`;
- в разделе экрана логина добавлено явное указание фонового файла;
- добавлен markdown-превью-блок изображения:
  `![Фон страницы входа](assets/images/ReceiverFullScreenBackground.jpg)`.

### Действие 10.3
Обновлен `SuperAgent/Context/project-architecture.md`:
- добавлены новые элементы структуры `assets/images/ReceiverFullScreenBackground.jpg` и `styleguide.md`.

---
## Итерация #11
**Дата**: 2026-03-30
**Запрос**: Оформить пользовательский портал в стиле референс-дизайна; использовать фоновое изображение только на странице входа, остальные части оставить однотонными.

### Действие 11.1
Обновлен шаблон `src/services/portal/templates/login.html`:
- переработан визуальный стиль под палитру и типографику, близкую к Citrix Gateway (`#574f5b`, `#02a1c1`, светлые карточки, аккуратные границы);
- добавено разделение режимов:
  - `auth-page` (для неавторизованного пользователя) с фоном `url("/assets/images/ReceiverFullScreenBackground.jpg")`;
  - `portal-page` (после входа) с однотонным фоном `#f9f9f9`;
- обновлена структура экрана входа (оверлей-карточка поверх фонового изображения);
- обновлена структура пользовательского портала с однотонным фоном и сеткой карточек серверов;
- удален переключатель темы (светлая/тёмная), чтобы сохранить единый визуальный стиль.

### Действие 11.2
Обновлен `src/services/portal/app.py`:
- добавлен import `StaticFiles`;
- добавлен mount `"/assets"` -> локальная папка `assets/`, чтобы фоновое изображение и другие ассеты были доступны в UI.

### Действие 11.3
Обновлен `SuperAgent/Context/project-architecture.md`:
- добавлено описание новой роли `templates/login.html`;
- зафиксировано подключение статики `/assets` в portal app.

---
## Итерация #12
**Дата**: 2026-03-30
**Запрос**: Исправить `404 Not Found` для `/assets/images/ReceiverFullScreenBackground.jpg`.

### Действие 12.1
Диагностирована причина:
- в `portal` приложении route `/assets` монтируется только при наличии директории `/app/assets`;
- в Docker image директория `assets` отсутствовала, так как не копировалась в `Dockerfile`.

### Действие 12.2
Исправлен `Dockerfile`:
- добавлена строка `COPY assets/ ./assets/`.

### Действие 12.3
Обновлен `SuperAgent/Context/project-architecture.md`:
- добавлено примечание о копировании `assets` в контейнер для корректной раздачи статических файлов портала.

---
## Итерация #13
**Дата**: 2026-03-30
**Запрос**: Добавить параметр «Наименование портала» (значение `DC319`), использовать его в `<title>` пользовательского портала, растянуть серую площадку под формой входа на всю ширину экрана, убрать верхнюю серую полосу с надписью `RDP Proxy Portal`.

### Действие 13.1
Обновлен API настроек `src/services/admin/routes/settings.py`:
- добавлен ключ `portal` в `_MERGE_KEYS`;
- в `GET /api/admin/settings` добавлен дефолт:
  - `portal: { name: "DC319" }`.

### Действие 13.2
Обновлен UI админ-настроек `src/services/admin/templates/admin_settings.html`:
- добавлена новая вкладка **Портал**;
- добавлено поле **Наименование портала** (`portal_name`);
- добавлено сохранение значения в ключ `portal` (`{ name: ... }`) через существующий endpoint `PUT /api/admin/settings`.

### Действие 13.3
Обновлены зависимости и роуты portal:
- `src/services/portal/dependencies.py`:
  - добавлен `get_portal_name()` с чтением `portal.name` из `portal_settings` и fallback `DC319`;
- `src/services/portal/routes/auth.py`:
  - `_render_login_page` переведен в async;
  - в контекст шаблона добавлен `portal_name`;
- `src/services/portal/routes/servers.py`:
  - в контекст шаблона добавлен `portal_name` как для гостя, так и для авторизованного пользователя.

### Действие 13.4
Обновлен шаблон `src/services/portal/templates/login.html`:
- `<title>` теперь формируется из `{{ portal_name }}` (fallback `DC319`);
- удалена верхняя серая полоса/хедер с текстом `RDP Proxy Portal`;
- добавлена полноширинная серая подложка `auth-band` под формой входа (как в референсе);
- сохранено требование: фон-изображение только на странице входа, авторизованная часть портала остается с однотонным фоном.

### Действие 13.5
Обновлен `SuperAgent/Context/project-architecture.md`:
- зафиксированы новые зависимости и поведение `portal_name`/`auth-band`/settings `portal`.

### Действие 13.6
Пересобраны и перезапущены сервисы для применения изменений Python/HTML:
```bash
docker compose up -d --build portal admin
```

### Действие 13.7
После пересоздания `portal/admin` через ingress `8443` наблюдался `503` из-за устаревшего backend-адреса в HAProxy (после смены container IP).
Выполнен перезапуск HAProxy:
```bash
docker compose restart haproxy
```

### Действие 13.8
Проверка результата:
- пользовательский портал отдает HTML с `<title>DC319</title>`;
- endpoint фонового изображения доступен;
- `portal` и `admin` в статусе `healthy`.

### Действие 13.9
По уточнению UX переработан экран входа в `src/services/portal/templates/login.html`:
- удален отдельный DOM-блок `section.auth-card`;
- форма входа перенесена внутрь `div.auth-band`;
- высота `auth-band` изменена с `170px` на `292px` (высота формы);
- полоса и форма теперь визуально единый центральный блок.

### Действие 13.10
Применение изменений:
```bash
docker compose up -d --build portal
```
Проверка через ingress:
```bash
curl -k -I https://127.0.0.1:8443/
```
Ответ получен от portal (HTTP 405 на HEAD, что ожидаемо для endpoint с методом GET).

### Действие 13.11
Дополнительная правка по уточнению DOM:
- в `src/services/portal/templates/login.html` удален контейнер `div.auth-form-wrap`;
- заголовок и форма логина рендерятся напрямую внутри `div.auth-band`;
- обновлены CSS-правила выравнивания/ширины для `auth-band`, `auth-title`, `auth-form`, `error`, чтобы сохранить центрирование без дополнительной обертки.

### Действие 13.12
Изменена прозрачность полосы входа:
- в `src/services/portal/templates/login.html` для `.auth-band` установлено
  `background: rgba(63, 54, 67, 0.75)`.

### Действие 13.13
Редизайн интерфейса после входа (`src/services/portal/templates/login.html`):
- добавлена верхняя тёмная панель:
  - слева заголовок сервиса (`portal_name`, сейчас `DC319`);
  - по центру пункт меню `Рабочие столы`;
  - справа имя пользователя, кнопка `Выход` и квадратная кнопка переключения темы (dark/light);
- добавлен JS-переключатель темы для авторизованной страницы с сохранением в `localStorage`.

### Действие 13.14
Обновлены плитки рабочих столов:
- кнопка `Скачать RDP` удалена;
- каждая плитка теперь содержит:
  - иконку `https://rd.dc319.ru:4433/vpn/media/Desktop.png`;
  - название сервера;
- плитка сделана кликабельной (`href="/rdp/<id>"`), скачивание `.rdp` запускается по клику на плитку.

### Действие 13.15
Дополнительная корректировка UI по уточнениям:
- в `src/services/portal/templates/login.html`:
  - заголовок в `header.portal-topbar > div.left` сделан белым, крупнее и жирнее (`24px`, `700`);
  - в `header.portal-topbar > div.right > button#themeToggle` заменено содержимое `1` на иконки `☀/☾`;
  - имя пользователя в правом блоке сделано белым в светлой теме;
  - под topbar добавлена узкая подпанель `portal-subbar` с поисковым полем справа;
  - реализован поиск по плиткам рабочих столов: фильтрация по первым буквам названия (case-insensitive, `startsWith`);
  - источник иконки плитки переключен на локальный `/assets/images/Desktop.png` (исключает блокировку CSP и проблему загрузки внешнего изображения).

### Действие 13.16
Подготовлен локальный ассет иконки рабочего стола:
- скачан `https://rd.dc319.ru:4433/vpn/media/Desktop.png`;
- сохранен в проект `assets/images/Desktop.png`.

### Действие 13.17
Удалена лишняя подпись в подпанели портала:
- из `src/services/portal/templates/login.html` удалены блок `div.portal-subbar-left` и связанные стили;
- у `.portal-subbar` выравнивание изменено на `justify-content: flex-end`, чтобы осталось только поле поиска справа.

---

## Итерация #14
**Время начала**: 2026-03-30
**Запрос**: Фон входа на весь экран; убрать белую полосу и лишний скролл на мобильном логине; после входа — мобильная шапка (бургер, активный пункт по центру, тема + иконка поиска), drawer с меню и выходом, раскрытие поиска с «Отмена».

### Действие 14.1
Файл `src/services/portal/templates/login.html`:
- для неавторизованной страницы: `viewport-fit=cover`, класс `auth-html` на `<html>`, фон на `body.auth-page` с `cover`, `min-height: 100dvh` / `-webkit-fill-available`, запасной `background-color`, `overflow-x: hidden`;
- `auth-viewport` с тем же минимумом высоты и flex-колонкой;
- портал: разметка `portal-topbar-main` (бургер, бренд/центр, правая зона), скрываемое на мобильном десктоп-меню и блок пользователя, `portal-search-banner` с полем и «Отмена», overlay + `portal-drawer` с навигацией и футером (логин + «Выйти»);
- стили и JS: открытие/закрытие drawer и поиска, синхронизация фильтра плиток между `desktopSearch` и `mobileSearchInput`, `Escape`.

### Действие 14.2
Обновлены `SuperAgent/Context/project-architecture.md` и `SuperAgent/Context/iterations-log.md` под мобильный UI портала и правки страницы входа.

---

## Итерация #15
**Время начала**: 2026-03-30 19:02:01
**Запрос**: Экран входа сломался, форма пропала.

### Действие 15.1
Исправлен способ центрирования формы на странице входа в `src/services/portal/templates/login.html`:
- у `.auth-viewport` включено flex-центрирование (`align-items: center`, `justify-content: center`, `padding: 24px 0`);
- у `.auth-band` удалено абсолютное позиционирование (`position: relative`, `top: auto`, `transform: none`, `width: 100%`).

### Действие 15.2
Обновлены `SuperAgent/Context/project-architecture.md` и `SuperAgent/Context/iterations-log.md` для фиксации исправления.

---

## Итерация #16
**Время начала**: 2026-03-30 19:04:19
**Запрос**: Форма входа должна быть строго посередине.

### Действие 16.1
Доработано центрирование формы в `src/services/portal/templates/login.html`:
- у `.auth-viewport` убран вертикальный отступ (`padding: 0`);
- у `.auth-band` заменено фиксированное `height` на `min-height: 292px`;
- `auth-band` переведен на `display: flex` с `flex-direction: column`, `align-items: center`, `justify-content: center`;
- внутренний отступ установлен `padding: 24px` для равномерного поля по всем сторонам.

### Действие 16.2
Обновлены `SuperAgent/Context/project-architecture.md` и `SuperAgent/Context/iterations-log.md` для фиксации корректировки центрирования.

---

## Итерация #17
**Время начала**: 2026-03-30 19:07:26
**Запрос**: Панель входа прилипла к верху, нужна строго по центру по вертикали.

### Действие 17.1
Уточнено центрирование полосы входа в `src/services/portal/templates/login.html`:
- в `.auth-viewport` отключено flex-центрирование, включено `overflow: hidden`;
- блок `.auth-band` переведен на `position: fixed` с привязкой `top: 50%` и `transform: translateY(-50%)`;
- ширина оставлена `100%`, чтобы полоса сохраняла полноширинный вид.

### Действие 17.2
Обновлены `SuperAgent/Context/project-architecture.md` и `SuperAgent/Context/iterations-log.md` после правки центрирования.

---

## Итерация #18
**Дата**: 2026-03-30
**Запрос**: RDP подключение не устанавливается с iPhone через приложение Windows App (ошибка 0x609).

### Действие 18.1
Добавлена runtime-инструментация в `handler.py`, `relay.py`, `mcs.py` для диагностики RDP lifecycle (NDJSON логирование в `/opt/rdpproxy-v2/.cursor/debug-b0044f.log`).

### Действие 18.2
Добавлен debug volume `./.cursor:/opt/rdpproxy-v2/.cursor` в `docker-compose.yml` для `rdp-relay`, чтобы логи были доступны с хоста.

### Действие 18.3
**Первый прогон**: iPhone (requestedProtocols=0x0B) подключился, прошёл TLS+CredSSP, но после MCS exchange сразу отключился (EOF после ~1 секунды). Причина: `patch_mcs_server` ставил `clientRequestedProtocols = PROTOCOL_SSL` (0x01) вместо оригинальных 0x0B клиента. iPhone строго проверяет это поле и отключается при несовпадении.

### Действие 18.4
**Первая попытка фикса (отклонена)**: передача requestedProtocols=0x0B напрямую в `connect_and_authenticate` для бэкенда. Это вызвало "Early User Authorization Result" (HYBRID_EX), которое сломало CredSSP-парсер. Backend сбросил соединение.

### Действие 18.5
**Корректный фикс**:
1. В `handler.py` добавлена функция `extract_requested_protocols()` из `rdp/x224.py` для извлечения оригинального `requestedProtocols` из X.224 CR клиента.
2. Значение сохраняется в `SessionContext.extra["client_requested_protocols"]`.
3. `credssp.py` — оставлен без изменений (бэкенд всегда получает `PROTOCOL_HYBRID` 0x03).
4. `plugins/mcs_patch.py` — передаёт `client_requested_protocols` из `ctx.extra` в `patch_mcs_server`.
5. `libs/rdp/mcs.py` — `patch_mcs_server(data, *, client_requested_protocols=None)` теперь патчит `clientRequestedProtocols` в SC_CORE на значение клиента (если передано), или fallback на `PROTOCOL_SSL`.

### Действие 18.6
**Верификация**: два успешных подключения iPhone (requestedProtocols=0x0B, SC_CORE: 0x03→0x0B, 74KB/151KB и 29KB/141KB, длительность 14 и 6 сек) + одно успешное подключение с ПК (requestedProtocols=0x01, SC_CORE: 0x03→0x01, 38KB/926KB). Фикс подтверждён runtime-доказательствами.

### Действие 18.7
Удалена вся debug-инструментация из `handler.py`, `relay.py`, `mcs.py`. Удалён debug volume из `docker-compose.yml`. Пересобран и перезапущен `rdp-relay`.

---
## Итерация #19
**Время начала**: 2026-04-06 16:00
**Запрос**: Оптимизация TCP throughput RDP relay — диагностика показала торможение из-за stop-and-wait drain, блокирующего sync Redis, малых TCP буферов
**Ответ**: Реализованы все 6 пунктов оптимизации

### Действие 19.1
**Описание**: relay.py — замена stop-and-wait drain на условный drain + увеличение буферов
**Изменения в `src/services/rdp_relay/relay.py`**:
- `READ_CHUNK`: 65536 → 131072 (128KB)
- Добавлены константы `WRITE_HIGH_WATER=512KB`, `WRITE_LOW_WATER=64KB`, `KILL_CHECK_INTERVAL=2.0`
- `_pipe()`: убран `asyncio.wait_for(reader.read(), timeout=POLL_TIMEOUT)` — заменён на прямой `reader.read(READ_CHUNK)`, что убирает 1-секундные таймауты при idle
- `drain()` вызывается только если `writer.transport.get_write_buffer_size() >= WRITE_HIGH_WATER` (условный drain вместо stop-and-wait)
- `tune_writer_buffers()` вызывается в начале `_pipe()` для поднятия asyncio transport water marks
- Параметр `kill_checker` заменён на `kill_event: asyncio.Event`
- Добавлена `_kill_poller()` — отдельная coroutine, которая запускает sync Redis GET в `run_in_executor` раз в 2 сек, не блокируя event loop

### Действие 19.2
**Описание**: tcp_utils.py — увеличение socket буферов, TCP_NODELAY, tune_writer_buffers
**Изменения в `src/services/rdp_relay/tcp_utils.py`**:
- `configure_tcp_keepalive()`: добавлено `SO_SNDBUF=512KB`, `SO_RCVBUF=512KB`, `TCP_NODELAY=1`
- Добавлена функция `tune_writer_buffers(writer, high, low)` для настройки asyncio transport write-buffer water marks

### Действие 19.3
**Описание**: docker-compose.yml — sysctls для контейнера rdp-relay
**Изменения в `docker-compose.yml`**:
- Контейнер `rdp-relay`: добавлена секция `sysctls` — `net.core.rmem_max=16MB`, `net.core.wmem_max=16MB`, `net.ipv4.tcp_rmem/wmem` max 16MB, `net.core.rmem_default/wmem_default=256KB`

### Действие 19.4
**Описание**: haproxy.cfg — корректные таймауты для long-lived RDP TCP
**Изменения в `deploy/haproxy/haproxy.cfg`**:
- `bk_rdp`: добавлены `timeout tunnel 24h` и `timeout client 24h` (ранее client наследовал 30s из defaults, что могло вызывать разрывы при idle)

### Действие 19.5
**Описание**: rdp_file.py — отключение UDP-пробы, TCP-only hint
**Изменения в `src/libs/rdp/rdp_file.py`**:
- `networkautodetect`: 1 → 0 (отключает попытку UDP multitransport, которую прокси не поддерживает — убирает 2-3 сек фолбек)
- Добавлен `connection type:i:6` (LAN, максимальная скорость) и `use redirection server name:i:0`

### Действие 19.6
**Описание**: Хостовые sysctls + docker-compose sysctls fix
- Убраны `net.core.rmem_default`/`wmem_default` из docker-compose (не namespaced, не поддерживаются в контейнере)
- Оставлены `net.ipv4.tcp_rmem` / `net.ipv4.tcp_wmem` с default 256KB и max 16MB
- Поднят хостовой `net.core.rmem_max`/`wmem_max` до 16MB через `sysctl -w` + `/etc/sysctl.conf`
- Пересобран и перезапущен `rdp-relay`
- Верификация: SO_SNDBUF 512KB→1MB (ядро удваивает), TCP_NODELAY=1, tcp_rmem/wmem max=16MB
- Все контейнеры Running/Healthy

---
## Итерация #20
**Время начала**: 2026-04-06
**Запрос**: 503 на портале после изменений
**Ответ**: HAProxy держал устаревший IP `portal`/`admin` после пересоздания контейнеров; добавлен runtime DNS через Docker 127.0.0.11

### Действие 20.1
**Описание**: `deploy/haproxy/haproxy.cfg` — секция `resolvers docker` (nameserver 127.0.0.11:53, `hold obsolete 0s`), на серверах `portal`, `admin`, `rdp-relay` добавлено `resolvers docker init-addr libc,none` для периодического пересоздания адресов.

### Действие 20.2
**Описание**: `timeout client 24h` перенесён с backend `bk_rdp` на frontend `ft_mux` (в backend `timeout client` игнорировался — предупреждение HAProxy). С `bk_rdp` удалён неэффективный `timeout client 24h`.

### Действие 20.3
Выполнен `docker compose restart haproxy`; проверка `http://portal:8001/health` из контейнера HAProxy — OK.

---
## Итерация #21
**Время начала**: 2026-04-06
**Запрос**: Включить BBR 3 сразу для снижения лагов при большой перерисовке
**Ответ**: В ядре доступен `bbr` (отдельного `bbr3` нет); включён `bbr` на хосте и в netns сервисов `haproxy`/`rdp-relay`, настройки сделаны персистентными

### Действие 21.1
Проверена поддержка congestion control:
- до загрузки модуля: `reno cubic`;
- после `modprobe tcp_bbr`: `reno cubic bbr`;
- отдельного `bbr3` нет в доступных алгоритмах ядра.

### Действие 21.2
Runtime-переключение на хосте:
- `net.core.default_qdisc=fq`;
- `net.ipv4.tcp_congestion_control=bbr`.

### Действие 21.3
Runtime-переключение в active netns контейнеров:
- `haproxy`: `tcp_congestion_control=bbr`;
- `rdp-relay`: `tcp_congestion_control=bbr`.

### Действие 21.4
Персистентные настройки:
- `docker-compose.yml`: добавлен `net.ipv4.tcp_congestion_control=bbr` в `sysctls` для `haproxy` и `rdp-relay`;
- `/etc/sysctl.conf`: добавлены `net.core.default_qdisc=fq`, `net.ipv4.tcp_congestion_control=bbr`.

### Действие 21.5
Применение и проверка:
- выполнен `docker compose up -d haproxy rdp-relay`;
- проверка через `nsenter`: в обоих netns `tcp_congestion_control=bbr`;
- контейнеры в статусе `Up`, `portal/admin` healthy.

---
## Итерация #22
**Время начала**: 2026-04-06
**Запрос**: После включения BBR предыдущая сессия зависла
**Ответ**: Это не возврат старого бага relay; зависание вызвано рестартом `haproxy/rdp-relay` во время активной сессии, остался stale `active` хвост в Redis/DB

### Действие 22.1
Проведена диагностика:
- В Redis найдены две active-сессии (`7ace...` и `857d...`), при этом в живых сокетах была только одна текущая;
- В PostgreSQL `connection_history` у `7ace...` оставался `status='active'` с пустым `ended_at`;
- Подтверждён сценарий stale-state после рестарта сервисов на живом трафике.

### Действие 22.2
Ручная консолидация состояния:
- удалён ключ `rdp:active:node-1:7ace...` из Redis;
- в PostgreSQL сессия `7ace...` закрыта как `status='error'`, `disconnect_reason='relay-restart'`.

### Действие 22.3
Добавлена защита от повторения:
- `src/libs/redis_store/active_tracker.py`: метод `reconcile_stale_active_on_startup()`;
- `src/services/rdp_relay/main.py`: вызов reconcile перед запуском listener.

### Действие 22.4
Применение:
- пересобран и перезапущен `rdp-relay`;
- подтверждение в логе: `Cleaned stale active sessions on startup: db=1 redis=1`.

---
## Итерация #23
**Дата**: 2026-04-08
**Запрос**: Добавить мониторинг качества TCP-соединения для активных RDP-сессий через Linux TCP_INFO и отображение метрик в Admin API.

### Действие 23.1
**Описание**: Добавлены GCC-константы в `src/libs/rdp/constants.py`:
- `TS_UD_CS_MSGCHANNEL = 0xC006`
- `TS_UD_CS_MULTITRANSPORT = 0xC00A`
- `TS_UD_SC_MULTITRANSPORT = 0x0C08`

### Действие 23.2
**Описание**: Создан новый плагин `src/services/rdp_relay/plugins/connection_quality.py`:
- Ctypes-структура `_TcpInfo` (31 поле из `struct tcp_info` Linux)
- Датакласс `QualitySnapshot` (rtt_ms, rtt_var_ms, jitter_ms, retransmits, total_retrans, lost, cwnd, rating)
- `ConnectionQualityPlugin(RdpPlugin)`:
  - `on_session_start`: достаёт сокеты из `ctx.extra`, запускает фоновую задачу `_monitor_loop`
  - `on_session_end`: отменяет задачу
  - `_monitor_loop`: первый замер через 2 сек, затем каждые 5 сек
  - `_sample()`: читает TCP_INFO с обоих сокетов, считает суммарный RTT и jitter по скользящему окну 20 замеров
  - Рейтинг: excellent (<20ms RTT, <5ms jitter, 0 retrans), good (<50ms, <15ms, <5), fair (<150ms, <40ms), poor
  - `_publish()`: обновляет существующий JSON в `rdp:active:{instance_id}:{connection_id}` полями `connection_quality` и `quality_detail`

### Действие 23.3
**Описание**: В `src/services/rdp_relay/handler.py` добавлена передача raw socket objects в `SessionContext.extra`:
- `client_socket = client_writer.get_extra_info("socket")`
- `backend_socket = backend.writer.get_extra_info("socket")`

### Действие 23.4
**Описание**: В `src/services/rdp_relay/main.py` импортирован и зарегистрирован `ConnectionQualityPlugin`:
- `ConnectionQualityPlugin(redis_client=redis_client, instance_id=config.instance.id)`

### Действие 23.5
**Описание**: В `src/services/admin/routes/sessions.py` добавлена модель и парсинг quality_detail:
- Pydantic-модель `QualityDetail` (rtt_ms, rtt_var_ms, jitter_ms, retransmits, total_retrans, lost, cwnd, rating)
- Поле `quality_detail: QualityDetail | None = None` в `ActiveSessionOut`
- Парсинг из Redis: `data.get("quality_detail")` → `QualityDetail(**qd_raw)`

### Действие 23.6
**Описание**: Пересобран и перезапущен контейнер `rdp-relay`:
```bash
docker compose up -d --build rdp-relay
```
Результат: плагин `connection_quality` зарегистрирован, сервис работает.

### Действие 23.7
**Описание**: Диагностика и исправление некорректных метрик (все сессии показывали "poor")

**Причина 1 — сдвиг структуры `_TcpInfo`**:
В ядре 6.8 (`linux/tcp.h`) поле `tcpi_last_ack_recv` присутствует между `tcpi_last_data_recv` и `tcpi_pmtu`. Оригинальная ctypes-структура (31 поле) его не учитывала, из-за чего все поля после offset 52 были сдвинуты на 4 байта. Плагин читал `rcv_ssthresh` вместо `rtt` (245-496ms вместо реальных 6-21ms) и `rcv_space` вместо `total_retrans`.

**Исправление**: добавлено поле `tcpi_last_ack_recv` (32 поля, 104 байта). Верификация через `ss -ti` и raw-дамп getsockopt подтвердила корректность.

**Причина 2 — кумулятивный `total_retrans` в рейтинге**:
Рейтинг использовал `total_retrans` (lifetime counter), который неизбежно рос до десятков тысяч. Заменён на дельту ретрансмиссий между замерами (`retrans_per_interval`).

**Причина 3 — слишком жёсткие пороги RTT**:
Измерение суммирует два плеча (клиент→прокси + прокси→бэкенд). Пороги увеличены:
- excellent: RTT < 50ms, jitter < 10ms, retrans/interval = 0
- good: RTT < 150ms, jitter < 30ms, retrans/interval < 10
- fair: RTT < 400ms, jitter < 80ms
- poor: остальное

**Результат**: сессия с реальным RTT ~19ms корректно показывает "excellent".

---
## Итерация #24
**Дата**: 2026-04-08
**Запрос**: Комплексная доработка админ-панели (28 пунктов UI/UX + 10 пунктов дашборда)

### Действие 24.1 — Блок 1: portal_name в шаблоны
- `app.py`: добавлен хелпер `_load_portal_name()` с кэшем в `app.state.portal_name_cache`, инвалидация при сохранении настроек
- `auth.py`: `_render_login_page` стала async, передаёт `portal_name` в контекст
- Все HTML-страницы теперь получают `portal_name` через `_make_handler`

### Действие 24.2 — Блок 9.1: Исправление ключей Redis в stats.py
- Ключи `rdp:metrics:latest` / `rdp:metrics:series` заменены на `rdp:metrics:{instance_id}:latest` / `rdp:metrics:{instance_id}:series`
- Добавлен параметр `period` (1h/6h/24h) с маппингом на количество точек
- `overview` теперь считает активные сессии через `rdp:active:*` ключи Redis, убран `total_sessions`

### Действие 24.3 — Блок 9.2: Расширение collector.py
- `_snapshot()` расширен: cpu_load_1/5/15, cpu_name, cpu_freq_mhz, swap_total/used/percent, net_bytes_sent_sec/recv_sec (дельта)
- Добавлены `self._prev_net`, `self._prev_ts` для расчёта дельты сетевого трафика
- CPU name/freq кэшируются при старте коллектора

### Действие 24.4 — Блоки 2+3: admin_base.html + admin_login.html
- `title` и sidebar `<h2>` используют `{{ portal_name }}`
- Блок пользователя перенесён из main-header в sidebar (username + "Выйти")
- "История" → "История подключений", убран пункт "Администраторы" из навигации
- Login: title и h1 используют `{{ portal_name }}`

### Действие 24.5 — Блок 4: admin_servers.html (7 правок)
- Убрана кнопка "Копия в форму" и её обработчик
- Кнопка "Удалить" перенесена в каждую строку таблицы
- Галочка "Активность" перенесена вверх формы с inline-стилем
- Поле "Порядок сортировки" скрыто (display:none)
- Порядок колонок: Название → Tech name (и в форме)
- Drag перенесён на `<tr>` целиком (draggable="true" на строке)

### Действие 24.6 — Блок 5: admin_templates.html (4 правки)
- Исправлена инициализация: убран `resetForm()` из IIFE, форма инициализируется через `loadTemplates()`
- Убраны JSON textarea и кнопка Preview
- Добавлено динамическое превью (`#previewBox`) с дебаунсом 400ms через `syncParams()`
- Секции local_resources и experience теперь рендерятся корректно

### Действие 24.7 — Блок 6: admin_sessions.html (6 правок) + kill-all
- "Куда (имя)" → "Имя сервера"
- Колонка "Порт" убрана, объединена с "Сервер" (address:port)
- Формат даты: ДД.ММ.ГГГГ чч:мм:сс (UTC+N) с определением часового пояса браузера
- Фильтры: убран фильтр начала, "Качество" → select, "Узел" → select (динамический)
- Добавлена кнопка "Завершить все сессии" + endpoint `POST /api/admin/sessions/kill-all`
- Убрана подсказка о фильтрах, кнопка очистки перенесена в top-bar

### Действие 24.8 — Блок 7: admin_history.html (3 правки)
- Колонки унифицированы с сессиями: "Имя сервера", "Сервер (адрес:порт)", формат дат
- Активные сессии исключены: `exclude_active=True` по умолчанию в API
- Фильтры: "Статус" → select (closed/killed/error), "Имя сервера" → select (загружается с API)

### Действие 24.9 — Блок 8: admin_settings.html (5 правок)
- Вкладки объединены: "Портал" → "Общие" (+ поля proxy), вкладка "Прокси" убрана
- "Разрешённые IP" перенесены в "Безопасность", вкладка "Админка (IP)" убрана
- Добавлена вкладка "Администраторы" (встроено содержимое admin_admin_users.html)
- Добавлен restart-баннер с кнопкой перезапуска + endpoint `POST /api/admin/services/restart`
- Чекбоксы выровнены через inline-check стиль

### Действие 24.10 — Блок 9.3: admin_dashboard.html
- Виджеты: CPU (название, частота, ядра, %, load 1/5/15), RAM (used/total, %), SWAP, Активные сессии, Сеть (↓↑)
- Убраны виджеты: "Всего сессий в БД", "RSS процесса", "TCP соединений"
- Добавлены переключатели периода (1ч/6ч/24ч)
- 4 графика: CPU%, RAM%, SWAP%, Сеть (входящий/исходящий)
- Графики с временными метками на оси X, сеткой, легендой

### Действие 24.11 — Почему UI «не менялся» в Docker
- В `docker-compose.yml` у `admin` и `metrics` был только том `config.yaml`; код и шаблоны попадали в контейнер только при `docker compose build`.
- Добавлены тома `./src:/app/src:ro` для сервисов `admin` и `metrics`, чтобы правки шаблонов/Python подхватывались после `docker compose up -d --force-recreate admin` без обязательной пересборки образа.

---
## Итерация #25
**Время начала**: 2026-04-08
**Запрос**: Исправить формат portal_name: «{Название} — Администратор» на странице входа и в title, название проекта в меню

### Действие 25.1 — Дефолт portal_name
- В `app.py` `_load_portal_name()` дефолт изменён с `"RDP Proxy"` на `"DC319"` (совпадает с дефолтом формы настроек)

### Действие 25.2 — admin_login.html
- `<title>` с `Вход — {{ portal_name }}` → `{{ portal_name }} — Администратор`
- `<h1>` с `{{ portal_name }}` → `{{ portal_name }} — Администратор`

### Действие 25.3 — admin_base.html
- `<title>` с `{Раздел} — {{ portal_name }}` → `{Раздел} — {{ portal_name }} — Администратор`
- Sidebar `<h2>` — без изменений, уже показывает `{{ portal_name }}`

### Проверка
- `title: DC319 — Администратор`, `h1: DC319 — Администратор` ✓
- Sidebar h2: `{{ portal_name }}` → `DC319` ✓

### Действие 25.4 — admin_base.html: title без «Администратор» на внутренних страницах
- `<title>` изменён на `{{ portal_name }} — {Раздел}` (формат: DC319 — Дашборд)

---
## Итерация #26
**Время начала**: 2026-04-08
**Запрос**: Шаблоны: кнопку удаления — в таблицу (как серверы), добавить проверку ошибок

### Действие 26.1 — admin_templates.html: кнопка «Удалить» в таблице
- Добавлены стили `.btn`, `.btn-danger`, `.btn-sm`
- В `renderTemplates()`: каждая строка получила кнопки «Изменить» + «Удалить» (по аналогии с серверами)
- Кнопка «Удалить» disabled для шаблона по умолчанию (с title-подсказкой)
- Удалена кнопка «Удалить» из формы редактирования

### Действие 26.2 — Валидация и обработка ошибок
- `saveTemplate()`: проверка пустого имени; confirm при смене шаблона по умолчанию
- `deleteTemplate(id)`: принимает id напрямую; блокирует удаление default-шаблона на фронте
- Обработчик кликов по таблице: поддержка обоих действий `edit`/`delete` (как в серверах)
- Бэкенд (templates.py): IntegrityError при дублировании имени → 409 с понятным сообщением

### Действие 26.3 — templates.py: group_details
- Добавлен `group_details` в `TemplateOut` (аналог серверов)
- `_load_group_name_map()` резолвит GUID → CN через `AdGroupCache`
- Все вызовы `_to_out()` обновлены, передают `group_name_map`
- Фронтенд: таблица и `fillForm()` используют `group_details` с CN-именами

---
## Итерация #27
**Время начала**: 2026-04-08
**Запрос**: Переработка страницы «История подключений» — фильтры, автоприменение, пагинация

### Действие 27.1 — sessions.py: новые фильтры API
- Добавлены параметры `server_display` (ilike), `disconnect_reason` (ilike)
- Добавлены `ended_from`, `ended_to` — фильтрация по `ended_at`
- Существующие `from`/`to` по-прежнему фильтруют `started_at`

### Действие 27.2 — admin_history.html: полная переработка
- **Фильтры в заголовках таблицы**: text-input для Логин, Имя сервера, IP, Причина; select для Статус; datetime-local пары (С/По) для Начала и Конца сессии
- **Автоприменение**: input → debounce 400ms → load(); change (select/datetime) → мгновенная загрузка
- **Кнопка «Сбросить фильтры»** в top-bar, очищает все поля и перезагружает
- **Forum-style пагинация**: номера страниц (1, 2, 3 ... 461, 462, 463), текущая выделена, стрелки «‹» и «›», быстрый переход кликом
- Убраны кнопки «Применить», «Назад»/«Вперёд», старый div.filters
- Сохранены: CSV-экспорт, выбор кол-ва на страницу

---
## Итерация #28
**Время начала**: 2026-04-08
**Запрос**: Виджет сети показывает 0 — исправить сбор сетевых метрик

### Действие 28.1 — docker-compose.yml: монтирование /proc хоста
- Добавлен volume `/proc:/host/proc:ro` в сервис `metrics`
- Это даёт доступ к `/host/proc/1/net/dev` — сетевому пространству хоста (PID 1 = init)

### Действие 28.2 — collector.py: чтение хостовой сети
- `_read_host_net()` теперь читает `/host/proc/1/net/dev` вместо контейнерного `/proc/net/dev`
- Суммирует трафик по всем интерфейсам кроме lo
- Fallback на `psutil.net_io_counters()` при ошибке

### Действие 28.3 — admin_dashboard.html: fmtBps улучшение
- При значениях < 1 КБ/с показывает «Б/с» вместо «0 КБ/с»
- При >= 1 КБ/с показывает 1 десятичный знак (было .toFixed(0))

**Результат**: метрики показывают реальный хостовой трафик (~240 КБ/с recv, ~198 КБ/с sent)

---
## Итерация #29
**Время начала**: 2026-04-08
**Запрос**: Подровнять информацию в плашках виджетов дашборда

### Действие 29.1 — CSS: единообразная структура KPI-карточек
- `.kpi`: добавлен `display: flex; flex-direction: column; min-height: 110px` — все карточки одинаковой высоты
- `.kpi .sub`: `margin-top: auto` — подписи прижаты к низу
- `.kpi .net-row`, `.dir`, `.net-val` — отдельные стили для симметричного отображения входящего/исходящего трафика

### Действие 29.2 — HTML: переструктуризация виджетов
- **Процессор**: `val` (%) вверху, детали (имя, ядра, частота, Load) внизу через `.sub`
- **Память / Swap**: без изменений (уже корректно)
- **Активные сессии**: добавлена подпись «Всего за сегодня: N»
- **Сеть**: ↓ и ↑ отображаются как две строки `.net-row` одинакового размера, подпись «Входящий / Исходящий» внизу

### Действие 29.3 — stats.py: today_connections в overview API
- Добавлен SQL-запрос `COUNT(*)` по `ConnectionHistory` за сегодняшний день (UTC)
- Возвращается в ответе `overview` как `today_connections`
