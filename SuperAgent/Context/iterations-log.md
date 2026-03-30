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
