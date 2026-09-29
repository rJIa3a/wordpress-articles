# Факт-чекинг черновика Microsoft Defender / Windows 11

Дата сверки: 29 сентября 2026 года. Итоговая редакция: `defender-factchecked.html`.

## Сверено с первичными источниками

| Утверждение в статье | Проверка |
| --- | --- |
| Переключатель защиты в реальном времени отключает её временно, а запланированные проверки продолжаются | Microsoft Support: https://support.microsoft.com/ru-ru/windows/security/threat-malware-protection/virus-and-threat-protection-in-the-windows-security-app |
| Совместимый сторонний антивирус меняет режим Microsoft Defender; при Smart App Control или Defender for Endpoint возможен пассивный режим | Microsoft Learn: https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-antivirus-compatibility |
| Поставщиков защиты можно найти через «Кто меня защищает?» → «Управление поставщиками» или параметры приложения | Microsoft Support: https://support.microsoft.com/ru-ru/windows/%D0%BF%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D0%BA%D0%B0-%D1%8D%D0%BB%D0%B5%D0%BC%D0%B5%D0%BD%D1%82%D0%B0-%D1%81-%D0%BF%D0%BE%D0%BC%D0%BE%D1%89%D1%8C%D1%8E-%D0%B1%D0%B5%D0%B7%D0%BE%D0%BF%D0%B0%D1%81%D0%BD%D0%BE%D1%81%D1%82%D0%B8-windows-d1c8c01d-12ed-e768-cbb8-830ea8ccf8e6 ; https://support.microsoft.com/ru-ru/windows/security/windows-security/windows-security-app-settings |
| Политика выключения Defender имеет ограничения, а при включённой защите от подделки изменение не применяется; Microsoft советует оставлять её ненастроенной | Microsoft Learn: https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-admx-microsoftdefenderantivirus#disableantispywaredefender |
| DisableAntiSpyware / DisableAntivirus являются устаревшими настройками развёртывания и игнорируются в указанных конфигурациях Defender for Endpoint | Microsoft Learn: https://learn.microsoft.com/en-us/windows-hardware/customize/desktop/unattend/security-malware-windows-defender-disableantispyware |
| Службы Defender нельзя считать безопасным универсальным способом отключения | Microsoft Learn: https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-antivirus-compatibility |
| Defender Control 2.1 выпущен в марте 2022 года; разработчик сообщил о прекращении обновлений и жалобах на восстановление защиты | Sordum: https://www.sordum.org/9480/defender-control-v2-1/ |
| Команда Get-MpComputerStatus читает состояние антивируса | Microsoft Learn: https://learn.microsoft.com/en-us/powershell/module/defender/get-mpcomputerstatus |

## Исправления после сверки

- Уточнена формулировка про исключения. Microsoft Support описывает исключения через приложение как относящиеся к проверке в реальном времени, тогда как актуальная Microsoft Learn документация описывает применение файловых исключений также к проверкам по расписанию и по запросу; исключение процесса имеет более узкую область. В статье теперь сказано только, что действие зависит от типа исключения и не распространяется на все функции защиты или другой антивирус. Источник: https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-antivirus-exclusions-overview
- Уточнён точный путь к странице поставщиков безопасности по справке Microsoft.
- Добавлен официальный русский снимок страницы параметров Microsoft Windows 11. Он показывает ссылку на управление поставщиками, но не результат установки другого антивируса.
- Подписи семи ранее добавленных снимков приведены к одному виду без сбившейся нумерации.
- Четыре служебные пометки о недостающих снимках удалены из читательского текста; задания сохранены ниже.

## Граница проверки

Фактическое исходное состояние Windows 11 Pro 25H2 было прочитано без изменения настроек: Defender Normal, AntivirusEnabled=True, RealTimeProtectionEnabled=True, IsTamperProtected=True. Это не испытание отключения. Отключение, результат после перезагрузки и восстановление защиты на тестовой системе не проверены. Собственных кадров приложения «Безопасность Windows» нет; текущие восемь снимков взяты из Microsoft Support и Hetman Software и подписаны. Снимки Hetman относятся к интерфейсу Windows 11 2021 года.

## Кадры для будущей самостоятельной съёмки

1. Русский экран «Исключения»: кнопка «Добавить исключение» и меню «Файл / Папка» с безвредным тестовым объектом, без личных путей.
2. Русский экран «Поставщики безопасности» после установки другого антивируса и перезагрузки: продукт и фактический статус.
3. Статус Defender после политики в Windows 11 Pro до и после перезагрузки: сборка Windows и версия платформы Defender в подписи.
4. Результат чтения `Get-MpComputerStatus` до и после действия. Не подменять его снимком выбранной политики или цветом сторонней утилиты.

Навык `computer-use` запрещает автоматизацию приложений безопасности Windows. Эти кадры необходимо получить при ручной проверке на отдельной тестовой системе, если редакция решит добавить собственную серию.
