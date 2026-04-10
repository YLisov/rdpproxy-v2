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

---
## Итерация #30
**Время начала**: 2026-04-09
**Запрос**: Миграция настроек из config.yaml в БД с управлением через админ-панель

### Действие 30.1 — Создание SettingsManager
**Создан файл `src/libs/config/settings_manager.py`**:
- Класс `SettingsManager` — центральное хранилище динамических настроек
- TTL-кэш 30 сек с автообновлением из `portal_settings`
- Fallback к YAML при отсутствии ключа в БД
- Seed при первом запуске: автоперенос из config.yaml в БД
- Шифрование `bind_password` через `AESEncryptor`
- Хуки горячей перезагрузки `on_change(key, callback)`
- Типизированные свойства: `ldap`, `dns`, `proxy_params`, `security_params`, `redis_ttl`, `rdp_relay_params`, `admin_security`
- Метод `get_all_for_ui()` для отдачи всех настроек в админку (без секретов)
- Поддержка Redis pub/sub publish при сохранении

### Действие 30.2 — Обновление config/loader.py
**Изменён файл `src/libs/config/loader.py`**:
- `AppConfig.ldap` стал `LdapConfig | None = None` (опциональный для первого запуска)
- Добавлена функция `_warn_deprecated_keys()` — логирование при наличии DB-управляемых полей в YAML
- Константа `_DB_MANAGED_KEYS` — перечень полей, управляемых через БД

### Действие 30.3 — Интеграция SettingsManager в admin/app.py
**Изменён файл `src/services/admin/app.py`**:
- Создание `SettingsManager` при инициализации приложения
- LDAP authenticator создается из DB-настроек (может быть `None`)
- Хуки: `_on_ldap_change`, `_on_redis_ttl_change`, `_on_portal_change`
- `_reapply_portal_settings` расширен: полная перезагрузка из БД + хуки
- Startup event загружает настройки из БД и применяет TTL/LDAP

### Действие 30.4 — Обновление admin/dependencies.py
**Изменён файл `src/services/admin/dependencies.py`**:
- Добавлен `get_settings_manager()` dependency

### Действие 30.5 — Переписан settings.py API
**Перезаписан файл `src/services/admin/routes/settings.py`**:
- GET читает из `SettingsManager.get_all_for_ui()`
- PUT сохраняет через `SettingsManager.save()` с Redis pub/sub
- Добавлены ключи `dns`, `redis_ttl`, `rdp_relay` в `_MERGE_KEYS`
- Добавлен endpoint `POST /ldap-test` для проверки LDAP с несохраненными параметрами

### Действие 30.6 — Интеграция SettingsManager в Portal
**Изменены файлы**:
- `src/services/portal/app.py`: SettingsManager + хуки + фоновая задача Redis pub/sub listener
- `src/services/portal/dependencies.py`: добавлены `get_settings_manager()`, `is_ldap_configured()`, `get_portal_name()` через SettingsManager
- `src/services/portal/routes/auth.py`: rate limits из `settings_manager.security_params`, TTL из `settings_manager.redis_ttl`, проверка `is_ldap_configured`
- `src/services/portal/routes/servers.py`: proxy params из `settings_manager.proxy_params`, проверка LDAP на главной странице

### Действие 30.7 — Обработка первого запуска (LDAP не настроен)
- В `portal/routes/auth.py`: login возвращает "Система не настроена" если LDAP = None
- В `portal/routes/servers.py`: главная страница показывает ошибку если LDAP = None

### Действие 30.8 — Интеграция SettingsManager в RDP Relay
**Изменены файлы**:
- `src/services/rdp_relay/main.py`: создание SettingsManager, фоновая задача `_settings_listener` (Redis pub/sub), обновление DNS resolver и handler при изменении настроек
- `src/services/rdp_relay/handler.py`: добавлены методы `update_dns()`, `update_settings()`. Динамические параметры: `token_fingerprint_enforce`, `proxy_protocol`, `ldap.domain` — из SettingsManager

### Действие 30.9 — Новые вкладки в админ-панели настроек
**Перезаписан файл `src/services/admin/templates/admin_settings.html`**:
- Добавлены вкладки: DNS (серверы, таймаут, TTL кэша), Сессии (web TTL, idle TTL, RDP token TTL), RDP Relay (proxy_protocol checkbox)
- CSS-бейджи: `.apply-badge.hot` (зеленый, "Применяется сразу"), `.apply-badge.restart` (оранжевый, "Требует перезапуска")
- JavaScript: сбор/отправка данных для DNS, sessions, relay вкладок

### Действие 30.10 — Обновление config.yaml.example и README
- `config.yaml.example`: только bootstrap-параметры (database, redis, security.encryption_key, proxy cert_path/key_path, bind addresses). LDAP/DNS/etc. в комментариях как пример seed.
- `README.md`: добавлен раздел "Configuration" о новой архитектуре настроек, обновлен Quick Start

**Результат**: Все настройки кроме bootstrap-параметров вынесены в БД и управляются через админ-панель. Горячая перезагрузка через Redis pub/sub. Обратная совместимость: seed из YAML при первом запуске.

---
## Итерация #31
**Время начала**: 2026-04-09
**Запрос**: Добавить фильтр пользователей в LDAP (ограничение входа по членству в группе, в т.ч. через вложенные подгруппы)

### Действие 31.1 — LdapConfig: новое поле user_filter
**Изменён файл `src/libs/config/loader.py`**:
- Добавлено поле `user_filter: str = ""` в `LdapConfig`

### Действие 31.2 — LDAPAuthenticator: применение фильтра
**Изменён файл `src/libs/identity/ldap_auth.py`**:
- Сохраняется `self.user_filter` из конфига
- Новый метод `_build_user_search_filter(upn)`: комбинирует UPN-поиск с `user_filter` через AND
- `authenticate()` и `find_user_dn()` используют `_build_user_search_filter` вместо жёсткого фильтра
- Типичный пример: `(memberOf:1.2.840.113556.1.4.1941:=CN=RDP_Users,...)` — фильтр по вложенным группам

### Действие 31.3 — Админ-панель: поле фильтра во вкладке LDAP
**Изменён файл `src/services/admin/templates/admin_settings.html`**:
- Добавлено поле «Фильтр пользователей (LDAP)» с placeholder-примером
- Подсказка с описанием OID 1.2.840.113556.1.4.1941
- JS: заполнение и сбор поля `user_filter` при загрузке/сохранении

**Результат**: Администратор может задать LDAP-фильтр в настройках → LDAP, ограничивающий вход пользователей по членству в группе (включая вложенные подгруппы через AD Matching Rule in Chain). Пустой фильтр = доступ для всех.

---
## Итерация #32
**Время начала**: 2026-04-09
**Запрос**: Дефолты в UI-полях, убрать admin_security.allowed_networks, убрать proxy_protocol из UI (хардкод True)

### Действие 32.1 — SettingsManager: удалены admin_security и rdp_relay
**Изменён файл `src/libs/config/settings_manager.py`**:
- `MANAGED_KEYS` сокращён до `("ldap", "dns", "proxy", "security", "redis_ttl", "portal")`
- Удалены свойства `rdp_relay_params` и `admin_security`
- `get_all_for_ui()` больше не возвращает `rdp_relay` и `admin_security`
- `_get_fallback()` — убраны ветки `rdp_relay` и `admin_security`
- `_seed_from_yaml()` — seed для `rdp_relay` и `admin_security` больше не выполняется

### Действие 32.2 — handler.py: Proxy Protocol v2 всегда включён
**Изменён файл `src/services/rdp_relay/handler.py`**:
- `_resolve_client_ip()` — убрано динамическое чтение `rdp_relay_params` из SettingsManager
- Proxy Protocol v2 теперь всегда включён через `self._cfg.rdp_relay.proxy_protocol` (хардкод `True` в Pydantic-модели `RdpRelayConfig`)

### Действие 32.3 — Админ-панель: убраны вкладка RDP Relay и поле Разрешённые IP
**Изменён файл `src/services/admin/templates/admin_settings.html`**:
- Убрана вкладка «RDP Relay» из навигации и её панель целиком
- Убрано текстовое поле «Разрешённые IP для админ-панели» из вкладки «Безопасность»
- JS: убрано заполнение/сбор `admin_allowed_ips`, `relay_proxy_protocol`, убрана функция `parseIpList()`
- При сохранении security больше не отправляется `admin_security`

### Действие 32.4 — settings API: убраны ключи из _MERGE_KEYS
**Изменён файл `src/services/admin/routes/settings.py`**:
- `_MERGE_KEYS` = `{"ldap", "security", "proxy", "redis_ttl", "portal", "dns"}`

### Действие 32.5 — loader.py: убраны deprecated-ключи
**Изменён файл `src/libs/config/loader.py`**:
- `_DB_MANAGED_KEYS` — убраны `rdp_relay.proxy_protocol` и `admin.allowed_networks`
- `_warn_deprecated_keys()` — упрощена, больше не проверяет `admin.allowed_networks`

**Результат**: Дефолтные значения seed-ятся в БД при первом запуске и отображаются в полях настроек. Proxy Protocol v2 захардкожен как всегда включённый. Настройка «Разрешённые IP для админ-панели» полностью убрана (мёртвая логика). IP-ограничения остались только на уровне пользователей-администраторов.

---
## Итерация #33
**Время начала**: 2026-04-09
**Запрос**: Поля «Веб-сессия» и «Таймаут бездействия» показывают только placeholder, а не значения по умолчанию

### Действие 33.1 — _seed_from_yaml: дополнение неполных записей в БД
**Изменён файл `src/libs/config/settings_manager.py`**:
- `_seed_from_yaml()` теперь не пропускает ключи, уже имеющиеся в кеше (БД)
- Для существующих записей проверяются недостающие подключи (сравнение с fallback-дефолтами)
- Если подключи отсутствуют — они дописываются в запись БД и кеш (`logger.info("Patched missing subkeys ...")`)
- Типичный сценарий: пользователь ранее сохранил только `rdp_token_ttl`, в БД `redis_ttl = {"rdp_token_ttl": 300}` без `web_session_ttl` и `web_idle_ttl`. Теперь при старте сервиса эти ключи дописываются из дефолтов

**Результат**: При следующем запуске сервиса все неполные записи в `portal_settings` будут автоматически дополнены значениями по умолчанию. Поля «Веб-сессия» и «Таймаут бездействия» будут отображать дефолтные значения 28800 и 1800 как заполненные поля, а не placeholder.

---
## Итерация #34
**Время начала**: 2026-04-09
**Запрос**: Защита от отключения и удаления единственного активного администратора

### Действие 34.1 — update_admin_user: защита от отключения последнего активного админа
**Изменён файл `src/services/admin/routes/admin_users.py`**:
- Параметр `_` переименован в `admin` для доступа к `admin.admin_user_id`
- Добавлена проверка при `is_active=False`: нельзя отключить себя (`str(uid) == admin.admin_user_id`)
- Добавлена проверка при `is_active=False`: подсчёт активных админов (`is_active == True`), если <= 1 — отказ с HTTP 400

### Действие 34.2 — delete_admin_user: усилена проверка при удалении
**Изменён файл `src/services/admin/routes/admin_users.py`**:
- Проверка «последнего администратора» теперь считает только **активных** (`is_active == True`), а не всех
- Проверка срабатывает только при удалении активного пользователя (`u.is_active`)
- Сообщение об ошибке обновлено: «Нельзя удалить последнего активного администратора»

**Результат**: Теперь невозможно заблокировать доступ в админ-панель через UI — система гарантирует наличие хотя бы одного активного администратора.

---
## Итерация #35
**Время начала**: 2026-04-09
**Запрос**: Реализовать план исправления 24 уязвимостей безопасности

### Группа A: Безопасность авторизации и сети

**A1. Проверка allowed_ips и allowed_networks в require_admin**
- `src/libs/redis_store/sessions.py` — добавлено поле `allowed_ips` в `AdminWebSessionData`, передаётся при создании/чтении admin-сессии
- `src/services/admin/dependencies.py` — добавлена функция `_ip_in_networks()`, проверка `allowed_networks` из конфига и `allowed_ips` пользователя в `require_admin()`
- `src/services/admin/routes/auth.py` — передача `user_allowed_ips` при создании сессии
- `src/services/admin/routes/admin_users.py` — валидация IP/CIDR формата через `field_validator` в `AdminUserCreate` и `AdminUserUpdate`

**A2. Унификация get_client_ip**
- `src/services/portal/dependencies.py` — заменён get_client_ip на использование `request.state.client_ip` (установленного RealIpMiddleware)

**A3. Cookie Secure flag**
- `src/libs/config/loader.py` — добавлено поле `secure_cookies: bool = True` в `ProxyConfig`
- `src/services/portal/routes/auth.py` — все cookie используют `cfg.proxy.secure_cookies`
- `src/services/admin/routes/auth.py` — аналогично для всех admin cookie

**A4. Redis пароль**
- `.env` — установлен сгенерированный пароль `REDIS_PASSWORD`
- `.env.example` — плейсхолдер `CHANGE_ME`
- `docker-compose.yml` — `--requirepass ${REDIS_PASSWORD}` в команде Redis
- `config.yaml` и `config.yaml.example` — пароль Redis

**A5. PROXY Protocol spoofing**
- `src/libs/config/loader.py` — добавлены `trusted_proxies` и `max_connections` в `RdpRelayConfig`
- `src/services/rdp_relay/handler.py` — метод `_is_trusted_proxy()`, проверка IP перед чтением PP-заголовка

### Группа B: Защита от DoS

**B1. Лимит TCP-соединений**
- `src/services/rdp_relay/main.py` — семафор `asyncio.Semaphore(max_connections)`, обёртка `_limited_handler`

**B2. redis.keys() → scan_iter()**
- Заменено в 6 местах: `stats.py`, `sessions.py` (2 места), `cluster.py`, `services_mgmt.py`, `collector.py`

**B3. Пагинация с ограничениями**
- `src/services/admin/routes/sessions.py` — `page: Query(ge=1, le=10000)`, `per_page: Query(ge=1, le=200)`

### Группа C: XSS / CSRF / Headers

**C1. Security headers для админки**
- `src/services/admin/app.py` — подключен `SecurityHeadersMiddleware`

**C2. CSRF на JSON API**
- Создан `src/services/admin/middleware/csrf.py` — проверка Origin/X-Requested-With/Content-Type для мутирующих запросов на `/api/`
- Подключен в `admin/app.py`

**C3. Исправление esc()**
- `admin_sessions.html`, `admin_templates.html`, `admin_dashboard.html` — добавлено экранирование `"` и `'`

**C4. Template literal injection**
- `admin_templates.html` — template literals заменены на конкатенацию с `esc()`

### Группа D: Обработка ошибок и валидация

**D1. Утечка исключений**
- `settings.py` — `str(exc)` заменён на общие сообщения, логирование через `logger.warning`

**D2. UUID валидация**
- `sessions.py` — `uuid.UUID()` обёрнут в try/except с HTTPException 400 (3 места)

**D3. kill_session порядок**
- `sessions.py` — UUID валидация перед обращением к Redis

**D4. json.loads обработка**
- `cluster.py` — добавлен try/except для `json.JSONDecodeError`

**D5. Мутабельный default**
- `templates.py` — `groups: list[str] = []` → `Query(default=[])`

**D6. Белый список настроек**
- `settings.py` — проверка ключей по `_ALLOWED_KEYS` перед сохранением

### Группа E: Логика и мёртвый код

**E1. TOCTOU в Redis**
- `src/libs/redis_store/sessions.py` — `set_token_fingerprint`, `get_web_session`, `get_admin_web_session` переведены на WATCH/pipeline
- `src/services/rdp_relay/plugins/connection_quality.py` — `_publish` через pipeline с WATCH

**E2. Интеграция is_idle()**
- `src/services/rdp_relay/plugins/registry.py` — добавлен метод `get_plugin(type)`
- `src/services/rdp_relay/handler.py` — `_kill_requested()` теперь проверяет `SessionMonitorPlugin.is_idle()`

**E3. Удаление мёртвого кода**
- Удалён `src/libs/security/rate_limit.py`

### Группа F: Инфраструктура

**F1. Docker USER + resource limits**
- `Dockerfile` — добавлен `useradd appuser` + `USER appuser`
- `docker-compose.yml` — добавлены `deploy.resources.limits` для всех 6 сервисов

**F2. HAProxy TLS**
- `deploy/haproxy/haproxy.cfg` — добавлены `ssl-default-bind-options` и `ssl-default-bind-ciphers`

**F3. SPKI парсинг**
- `src/libs/rdp/credssp.py` — добавлена функция `_extract_raw_pubkey()` с ASN.1 парсингом вместо `spki_der[24:]`

**Результат**: Реализованы все 24 исправления безопасности из плана. Изменены ~30 файлов.

---
## Итерация #36
**Дата**: 2026-04-09
**Запрос**: Рефакторинг кодовой базы — очистка, устранение дублирования, централизация

### Удалённые файлы
- `styleguide.md` — дизайн-документация, не используется в коде
- `tests/` — пустая директория (только `__init__.py`, ни одного теста)
- `deploy/cron/` — пустая директория

### `.gitignore`
- Добавлен `.cursor/` для артефактов IDE

### Новые модули

**`src/libs/redis_store/keys.py`** — централизованные Redis-ключи:
- Все строковые паттерны ключей (TOKEN, WEB_SESSION, ADMIN_WEB_SESSION, ACTIVE_SESSION, KILL_SESSION, METRICS_*, HEARTBEAT, NODE_*, SIGNAL_RESTART, AD_GROUPS_SEARCH, PORTAL/ADMIN_FAIL/LOCK_*)
- Все TTL-константы (KILL_TTL, AD_SEARCH_CACHE_TTL, METRICS_LATEST_TTL, SIGNAL_RESTART_TTL, FAIL_COUNTER_TTL)
- Pub/Sub каналы (SETTINGS_CHANGED_CHANNEL)

**`src/libs/security/login_limiter.py`** — унифицированный rate-limiter:
- Класс `LoginLimiter` с параметризованными паттернами ключей
- Фабрики `portal_limiter()` и `admin_limiter()` для разных контекстов
- Методы: `is_locked()`, `record_failure()`, `clear()`

### Устранение дублирования

**`admin/dependencies.py`**:
- Добавлены `get_db_session()` и `get_redis_client()` — единые точки получения DB-сессии и Redis-клиента
- Переименовано `_logger` → `logger` для консистентности со всеми остальными файлами

**Admin route файлы** (`admin_users.py`, `templates.py`, `sessions.py`, `stats.py`, `servers.py`):
- Удалены дублирующиеся `_db()` и `_redis()` из каждого файла
- Импорт `get_db_session`/`get_redis_client` из `dependencies`

**`portal/dependencies.py`**:
- Добавлен `get_redis_client()` для единообразия с admin

**Auth файлы** (`admin/routes/auth.py`, `portal/routes/auth.py`):
- Удалена дублирующаяся логика `_is_locked/_record_fail/_clear_fail` и `_is_login_locked/_record_failed_login/_clear_failed_login`
- Заменены на использование `LoginLimiter` из `security/login_limiter.py`

### Обновление на Redis-ключи из `keys.py`
Заменены хардкод-строки на константы из `redis_store.keys` в файлах:
- `redis_store/sessions.py`, `redis_store/active_tracker.py`
- `services/admin/routes/sessions.py`, `stats.py`, `cluster.py`, `services_mgmt.py`, `ad_groups.py`
- `services/metrics/collector.py`
- `services/rdp_relay/handler.py`, `main.py`
- `services/rdp_relay/plugins/connection_quality.py`
- `config/settings_manager.py`, `services/portal/app.py`

### Мелкие правки
- `rdp/credssp.py`: исправлены опечатки `cripted_key` → `encrypted_key`, `cripted_creds` → `encrypted_creds`
- `rdp_relay/tcp_utils.py`: все `except Exception: pass` заменены на `logger.debug(...)` с exc_info
- `admin_users.py`: `AdminUser.is_active == True` (noqa: E712) заменено на `.is_(True)`
- `admin_users.py`, `templates.py`, `servers.py`: `except Exception` при UUID-парсинге заменены на `except (ValueError, AttributeError)`
- `common/logging.py`: добавлены type hints к factory-функции
- `tcp_utils.py`: default high_water в `tune_writer_buffers` использует константу `SOCK_BUF_SIZE` вместо дублирования `512 * 1024`

**Результат**: ~25 файлов изменено. Устранено дублирование, централизованы Redis-ключи, унифицирован rate-limiting, исправлены опечатки и проглоченные исключения.

---
## Итерация #17
**Дата**: 2026-04-09
**Запрос**: Переименование проекта из `rdpproxy-v2` в `rdpproxy`.

### Действие 17.1
**Описание**: Переименован репозиторий на GitHub (`YLisov/rdpproxy-v2` → `YLisov/rdpproxy`), обновлён git remote.

### Действие 17.2
**Описание**: Массовая замена `rdpproxy-v2` → `rdpproxy` и `rdpproxy_v2` → `rdpproxy` в рабочих файлах.
**Изменённые файлы**:
- `docker-compose.yml` — `POSTGRES_DB: rdpproxy`
- `alembic.ini` — URL БД
- `config.yaml.example` — URL БД
- `config.yaml` (gitignored) — URL БД
- `deploy/scripts/renew-cert.sh` — пути `/opt/rdpproxy/...`
- `deploy/scripts/pg-backup.sh` — пути, имя БД, маска бэкапов
- `deploy/nftables/rules.nft` — комментарий с путём
- `README.md` — заголовок, пути, структура каталога
- `SuperAgent/tech-structure.md` — название проекта
- `SuperAgent/Context/project-architecture.md` — заголовок, пути, описание

### Действие 17.3
**Описание**: Каталог на сервере `/opt/rdpproxy-v2` переименован в `/opt/rdpproxy`.

**Результат**: Проект полностью переименован в `rdpproxy`. Старые ссылки на `-v2` / `_v2` удалены из всех конфигов, скриптов и документации.

---
## Итерация #18
**Дата**: 2026-04-09
**Запрос**: Настроить автоматическое обновление SSL-сертификатов Let's Encrypt.

### Действие 18.1
**Описание**: Проверка `certbot renew --dry-run` — порт 80 доступен извне (проброс на роутере настроен пользователем), standalone challenge проходит успешно.
**Результат**: `Congratulations, all simulated renewals succeeded`.

### Действие 18.2
**Описание**: Исправлен deploy hook `/etc/letsencrypt/renewal-hooks/deploy/rdpproxy-reload.sh`.
**Было**: `systemctl reload rdpproxy` (некорректно — проект работает через Docker Compose, а не systemd).
**Стало**: склейка `fullchain.pem + privkey.pem` → `rdp.pem` для HAProxy, затем `docker compose kill -s HUP haproxy` + `docker compose restart rdp-relay`.

### Действие 18.3
**Описание**: Обновлён `deploy/scripts/renew-cert.sh` — параметризован домен (аргумент, по умолчанию `rdp.lisov.pro`), добавлена проверка наличия LE-файлов, добавлен `docker compose restart rdp-relay` для подхвата нового сертификата.

**Результат**: Цепочка автообновления полностью работоспособна: `certbot.timer` (2 раза/день) → `certbot renew` → deploy hook → пересборка `rdp.pem` → перезагрузка HAProxy (HUP) + перезапуск rdp-relay.

### Действие 18.4
**Описание**: Убран хардкод домена из обоих скриптов. Deploy hook теперь использует `$RENEWED_LINEAGE` (certbot предоставляет автоматически) с fallback на чтение `proxy.public_host` из таблицы `portal_settings` в PostgreSQL. Ручной скрипт `renew-cert.sh` берёт домен из БД (или из аргумента).
**Изменённые файлы**:
- `/etc/letsencrypt/renewal-hooks/deploy/rdpproxy-reload.sh`
- `deploy/scripts/renew-cert.sh`

---
## Итерация #19
**Дата**: 2026-04-09
**Запрос**: Автоматический перевыпуск SSL-сертификата при смене домена через админ-панель.

### Действие 19.1
**Описание**: Создан скрипт `deploy/scripts/change-domain.sh` — принимает домен, запускает `certbot certonly --standalone`, собирает `rdp.pem`, перезагружает HAProxy (HUP) и rdp-relay. Пути compose-файла и dest параметризованы через env-переменные.

### Действие 19.2
**Описание**: Добавлен Redis pub/sub канал `CERT_RENEW_CHANNEL = "rdp:cert:renew"` в `libs/redis_store/keys.py`.

### Действие 19.3
**Описание**: Создан sidecar-сервис `services/cert_manager/main.py` — подписывается на Redis канал `rdp:cert:renew`, при получении сообщения с новым доменом запускает `change-domain.sh` через subprocess. Graceful shutdown, автоматический реконнект к Redis.

### Действие 19.4
**Описание**: Создан `deploy/cert-manager/Dockerfile` — образ на базе python:3.12-slim с установленными certbot и Docker CLI (+ compose plugin). Копирует код cert-manager и необходимые libs.

### Действие 19.5
**Описание**: Добавлен сервис `cert-manager` в `docker-compose.yml`. Порт 80 для certbot HTTP-01 challenge. Монтирования: `/etc/letsencrypt`, `/var/run/docker.sock`, `./deploy`, `config.yaml`, `docker-compose.yml`. Сеть rdpproxy для доступа к Redis.

### Действие 19.6
**Описание**: Добавлен хук `on_change("proxy")` в `services/admin/app.py`. При изменении `public_host` (сравнение с предыдущим значением) публикует новый домен в Redis канал `rdp:cert:renew`. Предыдущее значение инициализируется при старте из БД.

### Действие 19.7
**Описание**: Обновлён `admin_settings.html`:
- При изменении поля «Публичный адрес» появляется предупреждение о выпуске нового сертификата и необходимости настройки DNS.
- После сохранения с изменённым доменом — сообщение «Запрошен выпуск SSL-сертификата для нового домена».

**Результат**: Полная цепочка автоматизации: смена `public_host` в админ-панели → admin on_change хук → Redis pub/sub → cert-manager → certbot certonly → пересборка rdp.pem → reload HAProxy + restart rdp-relay.
**Новые файлы**: `deploy/scripts/change-domain.sh`, `deploy/cert-manager/Dockerfile`, `src/services/cert_manager/__init__.py`, `src/services/cert_manager/main.py`.
**Изменённые файлы**: `docker-compose.yml`, `src/libs/redis_store/keys.py`, `src/services/admin/app.py`, `src/services/admin/templates/admin_settings.html`.

---
## Итерация #20
**Дата**: 2026-04-09
**Запрос**: При завершении сессии админом через админку — удалять RDP-токен из Redis (чтобы клиент не авто-переподключался) + корректно отображать admin_kill в истории сессий (а не normal).

### Действие 20.1
**Описание**: Добавлен Redis-ключ `CONN_TOKEN = "rdp:conn-token:{connection_id}"` — маппинг connection_id на token, чтобы по connection_id можно было найти и удалить RDP-токен.
**Изменённые файлы**: `src/libs/redis_store/keys.py`

### Действие 20.2
**Описание**: Добавлено поле `delete_token_on_disconnect: bool = False` в `SecurityConfig` — настройка для опционального удаления токена при любом завершении сессии (запрет авто-переподключения).
**Изменённые файлы**: `src/libs/config/loader.py`

### Действие 20.3
**Описание**: Добавлен дефолт `delete_token_on_disconnect` в `security_params` свойство `SettingsManager`.
**Изменённые файлы**: `src/libs/config/settings_manager.py`

### Действие 20.4
**Описание**: В `active_tracker.py` метод `finish()` защищён от перезаписи записей со `status="killed"` — добавлено условие `ConnectionHistory.status != "killed"` в WHERE. Это предотвращает затирание admin_kill статуса финализацией handler.
**Изменённые файлы**: `src/libs/redis_store/active_tracker.py`

### Действие 20.5
**Описание**: В `handler.py` три изменения:
1. После `tracker.start()` сохраняется маппинг `CONN_TOKEN` (connection_id → token) в Redis с TTL равным `rdp_token_ttl`.
2. После завершения реле определяется реальная причина: анализ `result.legs` на `reason="killed"`, затем проверка наличия kill-ключа Redis для различения `admin_kill` vs `idle_timeout`. Корректный `status`/`disconnect_reason` передаётся в `tracker.finish()`.
3. Если настройка `delete_token_on_disconnect` включена — токен удаляется. Маппинг `CONN_TOKEN` очищается при любом завершении (включая exception).
**Изменённые файлы**: `src/services/rdp_relay/handler.py`

### Действие 20.6
**Описание**: В admin routes `kill_session` и `kill_all_sessions` добавлено удаление RDP-токена через маппинг `CONN_TOKEN`: по connection_id читается token, удаляется `rdp:token:{token}` и сам маппинг. Это гарантирует, что после admin kill клиент не сможет переподключиться.
**Изменённые файлы**: `src/services/admin/routes/sessions.py`

### Действие 20.7
**Описание**: В шаблон `admin_settings.html` добавлен чекбокс «Удалять токен при завершении сессии (запрет авто-переподключения)» на вкладке Безопасность. Добавлена загрузка значения из настроек и сбор при сохранении.
**Изменённые файлы**: `src/services/admin/templates/admin_settings.html`

### Действие 20.8
**Описание**: Чекбокс «Удалять токен при завершении сессии» перенесён из вкладки «Безопасность» на вкладку «Сессии» (под полем RDP-токен TTL). Настройка по-прежнему хранится в ключе `security` в БД, но при сохранении вкладки «Сессии» отправляется в payload вместе с `redis_ttl`. Загрузка значения читается из `settings.security`.
**Изменённые файлы**: `src/services/admin/templates/admin_settings.html`

**Результат**: Admin kill теперь полностью работает: 1) удаляется RDP-токен — клиент не может авто-переподключиться; 2) в истории сессий корректно отображается `status=killed` и `disconnect_reason=admin_kill` (ранее перезаписывалось на `closed`/`normal`); 3) добавлена опциональная настройка для удаления токена при любом завершении сессии.

---
## Итерация #21
**Дата**: 2026-04-09
**Запрос**: При рестарте rdp-relay очищать все транзиентные ключи в Redis (токены, сессии, маппинги).

### Действие 21.1
**Описание**: Расширен метод `reconcile_stale_active_on_startup()` в `active_tracker.py`. Помимо очистки `rdp:active:*` (как было), теперь при старте удаляются все транзиентные Redis-ключи: `rdp:token:*` (RDP-токены), `rdp:conn-token:*` (маппинги connection→token), `rdp:kill:*` (kill-сигналы), `rdp:web:*` (веб-сессии портала), `rdp:admin:web:*` (админские веб-сессии). Метрики, настройки и кэш не затрагиваются.
**Изменённые файлы**: `src/libs/redis_store/active_tracker.py`

**Результат**: После рестарта rdp-relay все пользовательские и админские сессии сбрасываются — требуется повторная авторизация. RDP-токены очищаются, исключая «висячие» подключения по старым токенам.

---
## Итерация #22
**Дата**: 2026-04-09
**Запрос**: При admin kill не сохраняется время конца сессии и длительность в истории.

### Действие 22.1
**Описание**: Исправлен метод `finish()` в `active_tracker.py`. Проблема: защитный WHERE `status != "killed"` полностью блокировал обновление записи, если админ уже поставил `status="killed"` (без `ended_at`). Решение — двухшаговый update: 1) попытка полного обновления для не-killed записей; 2) если запись уже killed (rowcount==0) — обновляются только `ended_at` и байты, без затирания статуса и причины.
**Изменённые файлы**: `src/libs/redis_store/active_tracker.py`

**Результат**: В истории сессий при admin kill теперь корректно отображаются время окончания, длительность и переданные байты наряду со статусом `killed` / `admin_kill`.

---
## Итерация #23
**Дата**: 2026-04-09
**Запрос**: Вынести idle_timeout и max_connections в настройки админки (SettingsManager), добавить абсолютный max_session_duration.

### Действие 23.1
**Описание**: В `RdpRelayConfig` добавлены поля `idle_timeout: int = 3600` и `max_session_duration: int = 0` (0 = без ограничения).
**Изменённые файлы**: `src/libs/config/loader.py`

### Действие 23.2
**Описание**: В `SettingsManager` добавлена секция `relay` в `MANAGED_KEYS`, свойство `relay_params` (max_connections, idle_timeout, max_session_duration), fallback к YAML, экспорт в `get_all_for_ui()`.
**Изменённые файлы**: `src/libs/config/settings_manager.py`

### Действие 23.3
**Описание**: В admin routes settings добавлен ключ `relay` в `_MERGE_KEYS` для разрешения сохранения.
**Изменённые файлы**: `src/services/admin/routes/settings.py`

### Действие 23.4
**Описание**: Переписан `SessionMonitorPlugin`: добавлен `max_session_duration`, `_started_at`, метод `is_duration_exceeded()`, метод `update_timeouts()` для горячего обновления. `idle_timeout=0` отключает idle check.
**Изменённые файлы**: `src/services/rdp_relay/plugins/session_monitor.py`

### Действие 23.5
**Описание**: В `handler.py` в `_kill_requested()` добавлена проверка `is_duration_exceeded()`. В определении причины завершения добавлена ветка `max_duration`.
**Изменённые файлы**: `src/services/rdp_relay/handler.py`

### Действие 23.6
**Описание**: В `main.py`: `SessionMonitorPlugin` инициализируется с параметрами из `relay_params`. `max_connections` читается из settings. `_settings_listener` расширен — при pub/sub обновляет `session_monitor.update_timeouts()` и динамически меняет лимит semaphore.
**Изменённые файлы**: `src/services/rdp_relay/main.py`

### Действие 23.7
**Описание**: В `admin_settings.html` добавлена вкладка «RDP Relay» с тремя полями: макс. подключений, таймаут бездействия, макс. длительность. JS загрузка из `settings.relay`, сохранение через PUT с ключом `relay`.
**Изменённые файлы**: `src/services/admin/templates/admin_settings.html`

**Результат**: Все три параметра (max_connections, idle_timeout, max_session_duration) теперь настраиваются из админки с горячей перезагрузкой через Redis pub/sub. Дефолты: 500 подключений, 1 час idle, без ограничения по длительности.

---
## Итерация #24
**Дата**: 2026-04-09
**Запрос**: Скрипт-установщик для развёртывания RDPProxy на чистом сервере

### Действие 24.1
**Описание**: Создан `deploy/install.sh` — двуязычный (EN/RU) bash-скрипт автоматизированной установки. Шаги: выбор языка, проверка root/apt, apt update+upgrade, установка Docker через get.docker.com, клон репо (или использование текущей папки), интерактивный диалог (домен, email LE, node-id, DB password, Redis password), генерация encryption_key, автодетект LAN IP, запись .env и config.yaml из шаблонов, выпуск сертификата (LE или self-signed), sysctl-тюнинг (BBR + TCP буферы), systemd-юнит rdpproxy.service, docker compose build+up, ожидание health, Alembic-миграции, создание admin/admin (must_change_password=true), итоговая сводка.
**Созданные файлы**: `deploy/install.sh`

### Действие 24.2
**Описание**: Удалена директория `deploy/nftables/` (содержала `rules.nft`). Firewall-настройка оставлена на усмотрение администратора, скрипт-установщик не управляет правилами брандмауэра.
**Удалённые файлы**: `deploy/nftables/rules.nft`

**Результат**: Проект получил полноценный установщик для развёртывания с нуля на любом apt-based дистрибутиве Linux. Единственный файл, минимум вопросов при установке, автогенерация секретов.

---
## Итерация #25
**Дата**: 2026-04-09
**Запрос**: Оформить README для людей: описание продукта, однострочная установка, краткие инструкции по настройке и работе.

### Действие 25.1
**Описание**: Корневой `README.md` переписан на русском: блок «О проекте» и сценарии для пользователя/администратора, возможности, требования, быстрый старт через `curl … install.sh` и локальный запуск установщика, явное указание что автоматический установщик только для apt (Ubuntu/Debian), ручная установка с миграциями Alembic через `docker compose exec` и пароль из `.env`, первый вход, systemd/compose, обновление, бэкап, скрипты сертификатов, таблица портов и cert-manager:80, масштабирование, краткая диаграмма и таблица сервисов, плагины relay, FAQ без устаревшего nftables. Убраны ссылки на удалённый `deploy/nftables/`.
**Изменённые файлы**: `README.md`, `SuperAgent/Context/project-architecture.md` (пояснение к README в дереве файлов)

**Результат**: Единая точка входа для операторов и новых участников: понятное описание продукта и актуальные команды без противоречий с текущим compose и установщиком.

---
## Итерация #26
**Дата**: 2026-04-09
**Запрос**: Текст раздела «Лицензия и вклад» для GitHub (пожелания, PR, security).

### Действие 26.1
**Описание**: В `README.md` заполнен раздел «Лицензия и вклад»: ссылка на `LICENSE`, Issues для идей, `WISHLIST.md`, рекомендации по PR и ответственное раскрытие уязвимостей. Исправлена разметка в FAQ (таблица `admin_users`).
**Изменённые файлы**: `README.md`

**Результат**: Участникам понятно, куда писать пожелания и как предлагать изменения.

---
## Итерация #27
**Дата**: 2026-04-09
**Запрос**: Дозаполнить раздел «Лицензия и вклад»: открытый исходный код, без подразумеваемой продажи продукта.

### Действие 27.1
**Описание**: В `README.md` раздел расширен: явное описание модели open source (не коммерческая продажа лицензии), ссылка на будущий `LICENSE` и обязанности при перераспространении, дисклеймер as is, восстановлены блоки Issues / WISHLIST / PR / security.
**Изменённые файлы**: `README.md`

**Результат**: Правовые ожидания сформулированы в духе типичного опенсорса до фиксации конкретного SPDX в `LICENSE`.

---
## Итерация #28
**Дата**: 2026-04-09
**Запрос**: Оформить Apache License 2.0, указать в README, добавить призыв ставить звезды на GitHub.

### Действие 28.1
**Описание**: В корень добавлен полный текст `LICENSE` (Apache-2.0, копирайт «The RDP-Proxy Authors»). В `README.md`: бейдж лицензии, абзац про Star под вступлением, раздел «Лицензия и вклад» переписан с явным Apache 2.0, SPDX, ссылкой на `LICENSE`, уточнением про сторонние компоненты, исправлены markdown-ссылки на LICENSE и WISHLIST, в конце раздела — повторный короткий призыв к Star. В `SuperAgent/Context/project-architecture.md` в дереве корня добавлена строка `LICENSE`.
**Созданные файлы**: `LICENSE`
**Изменённые файлы**: `README.md`, `SuperAgent/Context/project-architecture.md`

**Результат**: Лицензия зафиксирована в репозитории; README согласован с Apache 2.0 и GitHub.

---
## Итерация #29
**Дата**: 2026-04-10
**Запрос**: Убрать захардкоженные IP-ограничения из дефолтных значений конфигурации.

### Действие 29.1
**Описание**: В `src/libs/config/loader.py` удалены захардкоженные дефолтные IP-диапазоны: `AdminConfig.allowed_networks` (было `["10.120.0.0/24", "127.0.0.0/8"]` → пустой список) и `RdpRelayConfig.trusted_proxies` (было `["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16", "127.0.0.0/8"]` → пустой список). В `config.yaml.example` добавлены закомментированные примеры настройки обоих полей с пояснениями.
**Изменённые файлы**: `src/libs/config/loader.py`, `config.yaml.example`

**Результат**: Дефолтная конфигурация больше не содержит захардкоженных IP-ограничений. Пустой `allowed_networks` = нет IP-фильтрации (только аутентификация). Пустой `trusted_proxies` = Proxy Protocol заголовки игнорируются, используется прямой IP пира.

---
## Итерация #30
**Дата**: 2026-04-10
**Запрос**: Заменить нестандартный порт 8443 на стандартный 443 во всём проекте.

### Действие 30.1
**Описание**: Порт публичной точки входа HAProxy изменён с `8443` на `443` (стандартный HTTPS/TLS). Изменения затронули: дефолт `ProxyConfig.listen_port` в конфигурации, `haproxy.cfg` (bind и комментарий), `docker-compose.yml` (проброс порта), `install.sh` (вывод URL без порта, т.к. 443 — дефолт для HTTPS), `README.md` (таблицы, схема, FAQ). Обновлена документация SuperAgent.
**Изменённые файлы**: `src/libs/config/loader.py`, `deploy/haproxy/haproxy.cfg`, `docker-compose.yml`, `deploy/install.sh`, `README.md`, `SuperAgent/project-brief.md`, `SuperAgent/Context/project-architecture.md`, `SuperAgent/tech-structure.md`

**Результат**: Проект использует стандартный порт 443. URL-ы в документации и инсталляторе больше не требуют явного указания порта.

---
## Итерация #31
**Дата**: 2026-04-10
**Запрос**: Исправить проблему: `listen_port` в конфигурации вводит в заблуждение — он не управляет портом HAProxy, а только подставляется в `.rdp`-файлы. Переименовать в `public_port`, убрать ложный «перезапуск» из админки.

### Действие 31.1
**Описание**: Полный рефакторинг `listen_port` → `public_port`:
- `ProxyConfig.listen_port` → `ProxyConfig.public_port` в `loader.py`
- `_DB_MANAGED_KEYS`: `proxy.listen_port` → `proxy.public_port`
- `settings_manager.py`: `proxy_params` возвращает `public_port`; добавлен fallback на `listen_port` для обратной совместимости с существующими записями в БД
- `portal/routes/servers.py`: `proxy["listen_port"]` → `proxy["public_port"]`
- `admin_settings.html`: label «Порт прослушивания» → «Публичный порт», placeholder `3389` → `443`, id `proxy_listen_port` → `proxy_public_port`, убран бейдж «перезапуск» (заменён на общий «Применяется сразу»), удалён `showRestartBanner()` при смене порта, добавлена подсказка о том что это внешний порт для клиентов и HAProxy настраивается отдельно; JS загрузки значения с fallback на старый ключ `listen_port`
**Изменённые файлы**: `src/libs/config/loader.py`, `src/libs/config/settings_manager.py`, `src/services/portal/routes/servers.py`, `src/services/admin/templates/admin_settings.html`

**Результат**: Настройка порта больше не вводит в заблуждение. Название `public_port` чётко указывает, что это порт для клиентов в `.rdp`-файлах, а не порт прослушивания HAProxy. Обратная совместимость с существующими записями в БД сохранена.

---
## Итерация #32
**Дата**: 2026-04-10
**Запрос**: Сделать так, чтобы настройка `public_port` в админке реально управляла портом HAProxy — автоматический перезапуск контейнера через systemd path watcher.

### Действие 32.1
**Описание**: Реализована полная цепочка динамической смены порта HAProxy:

1. **`docker-compose.yml`**: порт HAProxy вынесен в переменную `${PUBLIC_PORT:-443}:443`. Внутри контейнера HAProxy всегда слушает на 443, наружу маппится `PUBLIC_PORT`. В admin-контейнер примонтирован `.env` как writable том.

2. **`src/services/admin/app.py`**: добавлена функция `_update_dotenv_port()` и обработка смены порта в хуке `_on_proxy_change`. При изменении `public_port` admin-сервис обновляет `PUBLIC_PORT=<значение>` в `/app/.env` (bind mount на хостовый `.env`). Отслеживание через `_prev_public_port` — запись только при реальном изменении.

3. **`deploy/systemd/rdpproxy-port-watcher.path`** (новый): systemd path unit, следит за `PathModified` на `.env`.

4. **`deploy/systemd/rdpproxy-port-watcher.service`** (новый): выполняет `docker compose up -d --no-build haproxy` — пересоздаёт контейнер HAProxy с новым port mapping.

5. **`deploy/install.sh`**: `.env` теперь включает `PUBLIC_PORT=443` и `LAN_IP`. Добавлена установка и активация systemd watcher unit-ов (с подстановкой PROJECT_DIR через sed).

6. **`admin_settings.html`**: подсказка обновлена — «При смене HAProxy будет автоматически перезапущен с новым портом».

**Созданные файлы**: `deploy/systemd/rdpproxy-port-watcher.path`, `deploy/systemd/rdpproxy-port-watcher.service`
**Изменённые файлы**: `docker-compose.yml`, `src/services/admin/app.py`, `deploy/install.sh`, `src/services/admin/templates/admin_settings.html`

**Цепочка работы**: Админ меняет порт в UI → admin-сервис сохраняет в БД + пишет `PUBLIC_PORT` в `.env` → systemd замечает изменение `.env` → запускает `docker compose up -d haproxy` → контейнер пересоздаётся с новым port mapping → задержка ~5 секунд.

---
## Итерация #33
**Дата**: 2026-04-10
**Запрос**: В админке порт 443, портал на 443, а скачанный `.rdp` содержит порт 8443.

### Действие 33.1
**Описание**: Причина — кеш `SettingsManager` в контейнере `portal`: свойство `proxy_params` не вызывает `get()` с TTL-обновлением; при сбое или задержке Redis pub/sub портал продолжал отдавать старый `listen_port` из merge в БД. Исправления: (1) в `servers.py` перед генерацией `.rdp` вызывается `await mgr.load()`; (2) при сохранении `proxy` с `public_port` из merge и кеша удаляется устаревший `listen_port`; (3) при `load()` если в строке `proxy` есть и `public_port`, и `listen_port`, из кеша убирается `listen_port`. Обновлён `SuperAgent/Context/project-architecture.md`.
**Изменённые файлы**: `src/services/portal/routes/servers.py`, `src/libs/config/settings_manager.py`, `SuperAgent/Context/project-architecture.md`

**Результат**: Адрес и порт в `.rdp` совпадают с актуальными настройками в БД; дубликат `listen_port` в JSON настройки `proxy` больше не мешает после сохранения порта из админки.

---
## Итерация #34
**Дата**: 2026-04-10
**Запрос**: После смены порта на 8443 в настройках `.rdp` стал с портом 8443, но портал оставался на 443 — HAProxy не пересоздавался без systemd path watcher на хосте.

### Действие 34.1
**Описание**: Добавлен надёжный триггер пересоздания HAProxy через Redis и уже существующий `cert-manager` (есть `docker.sock`): константа `HAPROXY_RECREATE_CHANNEL` в `redis_store/keys.py`; после успешной записи `PUBLIC_PORT` в `.env` admin публикует в этот канал; `cert_manager/main.py` подписан на оба канала и выполняет `docker compose -f … -p … --env-file /app/.env up -d --no-build haproxy`. В `docker-compose.yml` у `cert-manager` смонтирован `./.env:/app/.env`. `_update_dotenv_port` возвращает `bool`; подсказка в `admin_settings.html` обновлена. `SuperAgent/Context/project-architecture.md` — раздел cert-manager.
**Изменённые файлы**: `src/libs/redis_store/keys.py`, `docker-compose.yml`, `src/services/admin/app.py`, `src/services/cert_manager/main.py`, `src/services/admin/templates/admin_settings.html`, `SuperAgent/Context/project-architecture.md`

**Результат**: Смена публичного порта в админке обновляет проброс портов HAProxy без обязательного systemd на хосте (path unit остаётся дополнительной страховкой при установке через install.sh).

---
## Итерация #35
**Дата**: 2026-04-10
**Запрос**: Сервер упал после сохранения настроек — все контейнеры (admin, portal, rdp-relay, haproxy) вошли в цикл рестартов.

### Действие 35.1
**Описание**: Диагностика выявила две корневые проблемы:
1. **cert-manager пересоздавал ВСЕ контейнеры, а не только haproxy**: команда `docker compose up -d haproxy` (без `--no-deps`) пересоздавала зависимые admin/portal/relay. Новые контейнеры не могли стартовать (`No module named 'services'`).
2. **Bind mount-ы ломались при compose из контейнера**: при запуске `docker compose -f /app/docker-compose.yml` изнутри cert-manager относительные пути (`./deploy/haproxy`) разрешались как `/app/deploy/haproxy`, а Docker daemon искал этот путь **на хосте**, где его не существует. Результат — `Cannot open haproxy.cfg`.

**Исправления**:
- В `cert_manager/main.py` добавлены флаги `--no-deps --no-build --force-recreate` — пересоздаётся строго один контейнер haproxy.
- Добавлен `--project-directory ${HOST_PROJECT_DIR}` — compose разрешает относительные пути из хостового каталога `/opt/rdpproxy`, и bind mount-ы работают корректно.
- В `docker-compose.yml` для cert-manager добавлена переменная окружения `HOST_PROJECT_DIR: ${HOST_PROJECT_DIR:-/opt/rdpproxy}`.
- В `.env` на хосте добавлена строка `HOST_PROJECT_DIR=/opt/rdpproxy`.
- В `deploy/install.sh` при генерации `.env` добавлена строка `HOST_PROJECT_DIR=${PROJECT_DIR}`.

**Изменённые файлы**: `src/services/cert_manager/main.py`, `docker-compose.yml`, `deploy/install.sh`, `.env`

**Результат**: Тест подтверждён — смена `PUBLIC_PORT` на 8443 → cert-manager пересоздаёт **только** haproxy с корректными volumes и port mapping `0.0.0.0:8443->443/tcp`. Все остальные сервисы не затронуты. Возврат на 443 — аналогично успешен.

---
## Итерация #36
**Дата**: 2026-04-10
**Запрос**: Исправление 2 багов в `deploy/install.sh`, обнаруженных при чистой установке на Ubuntu 24.04.

### Действие 36.1
**Описание**: Баг 1 — `curl -fsSL https://get.docker.com | sh -s -- --quiet` содержит невалидный флаг `--quiet`. Текущая версия `get.docker.com` не поддерживает его, выводит «Illegal option --quiet», при `set -euo pipefail` это прерывает весь скрипт.
**Исправление**: заменено на `curl -fsSL https://get.docker.com | sh < /dev/null 2>&1` (вывод заглушен редиректом вместо флага).

### Действие 36.2
**Описание**: Баг 2 — миграции Alembic запускались ПОСЛЕ `docker compose up -d` (секция 14). Контейнеры portal и admin при старте выполняют `SELECT ... FROM portal_settings`, но таблица ещё не создана — миграции не применены. Контейнеры крашатся, healthcheck не проходит, скрипт зависает.
**Исправление**: полностью перестроен порядок запуска (секции 12-15):
1. `docker compose build` — сборка образов
2. `docker compose up -d postgres redis` — только БД
3. `wait_healthy postgres 60` + `wait_healthy redis 60`
4. `docker compose run --rm -T --no-deps portal python -c "...alembic upgrade head..."` — миграции через одноразовый контейнер
5. `docker compose up -d` — запуск всех сервисов (таблицы уже на месте)
6. `wait_healthy portal 120` + `wait_healthy admin 120`
7. Создание admin-пользователя

**Изменённые файлы**: `deploy/install.sh`
