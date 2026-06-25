<p align="center">
  <img src="custom_components/infolada/brand/logo.png" alt="ИнфоЛада" width="420">
</p>

<h1 align="center">ИнфоЛада для Home Assistant</h1>

<p align="center">
  Интеграция личного кабинета интернет-провайдера <strong>ИнфоЛада</strong> (Тольятти)
</p>

<p align="center">
  <a href="https://github.com/thebestbaduser/infolada-homeassistant/releases">
    <img src="https://img.shields.io/github/v/release/thebestbaduser/infolada-homeassistant?label=версия" alt="Version">
  </a>
  <a href="https://github.com/hacs/integration">
    <img src="https://img.shields.io/badge/HACS-Custom-orange" alt="HACS Custom">
  </a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.1+-blue" alt="Home Assistant">
</p>

---

Интеграция подключает Home Assistant к [личному кабинету ИнфоЛада](https://start.infolada.ru/auth?tab=portal) и создаёт сенсоры с балансом, тарифом, сроками действия и статусом услуг. Подходит для автоматизаций и уведомлений о пополнении счёта или окончании тарифа.

## Возможности

### Интернет

| Сенсор | Описание |
| --- | --- |
| Баланс | Текущий баланс лицевого счёта |
| Текущий тариф | Название активного тарифного плана |
| Дата начала тарифа | Когда подключён текущий тариф |
| Дата окончания тарифа | Когда тариф заканчивается |
| Дней до окончания тарифа | Остаток дней — удобно для уведомлений |
| Номер договора | Номер лицевого счёта / договора |
| Контрагент | Ф. И. О. владельца договора |
| Статус интернета | Текущее состояние доступа |
| Рекомендуемое пополнение | Сумма, которую рекомендует кабинет |
| Бонусы | Бонусный баланс (если доступен) |
| Остаток трафика | Остаток включённого трафика в МБ |
| Последнее обновление | Время последнего успешного опроса |

### Кабельное ТВ и телефония

Если услуги подключены, создаются отдельные устройства с балансом, тарифом, задолженностью и стоимостью.

## Установка через HACS

1. Установите [HACS](https://hacs.xyz/).
2. Добавьте custom repository:
   - **Repository:** `thebestbaduser/infolada-homeassistant`
   - **Category:** Integration
3. Установите интеграцию **Infolada**.
4. Перезагрузите Home Assistant.

## Настройка

1. **Настройки → Устройства и службы → Добавить интеграцию**
2. Найдите **Infolada** (логотип ИнфоЛада)
3. Введите логин и пароль от [личного кабинета](https://start.infolada.ru/auth?tab=portal)
4. Задайте интервал обновления (по умолчанию 6 часов)

## Пример автоматизации

Уведомление за 7 дней до окончания тарифа:

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.infolada_<login>_tariff_days_left
    below: 7
action:
  - service: notify.mobile_app
    data:
      title: "ИнфоЛада"
      message: >
        Тариф «{{ states('sensor.infolada_<login>_current_tariff') }}»
        заканчивается {{ states('sensor.infolada_<login>_tariff_date_off') }}.
        Осталось {{ states('sensor.infolada_<login>_tariff_days_left') }} дн.
```

## Как это работает

Интеграция использует тот же REST API, что и веб-кабинет `https://infolada.ru/lk/`:

- авторизация через `/lk/auth`;
- данные договора и счёта: `/api/v2/internet-contract`, `/api/v2/internet-account`;
- пользователи и тариф: `/api/v2/user/list`, `/api/v2/user/{id}`, `/api/v2/user-program/info/{id}`;
- КТВ и телефония: `/api/v2/ktv`, `/api/v2/telephone`.

Официального публичного API у провайдера нет — интеграция может перестать работать после изменений на стороне ИнфоЛады.

## Безопасность

Логин и пароль хранятся в конфигурации Home Assistant. Рекомендуется отдельный пароль для личного кабинета.

## Лицензия

MIT
