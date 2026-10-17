# Серверные нейроголоса

Qwen3-TTS-12Hz-0.6B-CustomVoice — открытая модель Apache 2.0 с поддержкой русского.
Это генеративный нейросинтез, не системный голос браузера. Предустановленные тембры
Serena/Vivian/Ryan/Aiden умеют говорить на русском, но их исходные языки не русский;
акцент и качество следует сравнить через «Прослушать голос». Не заявляем равенство
ElevenLabs без прослушивания. Модель и код: https://github.com/QwenLM/Qwen3-TTS.
Веса: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice.

## Linux CPU (x86_64)

В `.env`:

```dotenv
INSTALL_NEURAL=true
TTS_PROVIDER=qwen
QWEN_TTS_DEVICE=cpu
QWEN_TTS_SPEAKER=serena
QWEN_TTS_THREADS=4
QWEN_TTS_TIMEOUT_SECONDS=20
```

```sh
docker compose build delta-core
# Единственный этап, требующий сети для скачивания весов:
docker compose run --rm --no-deps -e HF_HUB_OFFLINE=0 delta-core \
  python -m delta_core.voice.provision_neural
docker compose up -d --no-deps delta-core delta-control-center
```

Модель хранится в отдельном постоянном volume `qwen-models`. Для существующей
директории можно задать `QWEN_MODEL_VOLUME=/absolute/path/to/qwen`. Provision закреплён
на revision `85e237c12c027371202489a0ec509ded67b5e4b5`. Во время работы загрузка
только с диска (`local_files_only=True`). Piper должен быть
установлен по обычной инструкции, иначе резерв будет недоступен. Docker image
использует отдельный lock с хешами, CPU torch 2.8.0, Python 3.12. Базовый Piper-образ
не получает тяжёлые зависимости при `INSTALL_NEURAL=false`.

Нейромодель расходует существенно больше памяти и CPU, чем Piper. На CPU этот
вариант подходит для проверки качества; приемлемую задержку нужно измерять на
целевом сервере. Для NVIDIA Linux подготовлен отдельный CUDA lock и Compose override:

```sh
docker compose -f docker-compose.yml -f docker/compose.neural-gpu.yml build delta-core
docker compose -f docker-compose.yml -f docker/compose.neural-gpu.yml run --rm --no-deps \
  delta-core python -m delta_core.voice.provision_neural
docker compose -f docker-compose.yml -f docker/compose.neural-gpu.yml up -d
```

Нужны NVIDIA GPU, совместимый драйвер и NVIDIA Container Toolkit. Override ставит
CUDA PyTorch, пробрасывает GPU и выбирает `cuda:0`; CPU-модель сохраняет float32,
GPU использует bfloat16/SDPA. CUDA-вариант не проверен на этом Mac без NVIDIA GPU.
Одной смены `QWEN_TTS_DEVICE` в CPU-образе недостаточно.

## Поведение

Настройки находятся на отдельной странице «Настройки ассистента» и сохраняются в
этом браузере. Сервер отдаёт каталог и флаг готовности через `/assistant/voice/config`.
Если модель не установлена, нейроголоса недоступны для выбора; это явно показано.

При занятом inference, ошибке или превышении `QWEN_TTS_TIMEOUT_SECONDS` ответ
переходит на Piper. Выполненное действие не повторяется. Поток, превысивший тайм-аут,
удерживает блокировку до фактического окончания; следующие запросы не создают очередь
нейросинтеза. Ограничены длина текста, число генерируемых токенов и длительность WAV.
Отмена ожидания не останавливает нативный inference; лимит токенов ограничивает его работу.

Пример выбранного нейроголоса ждёт до `QWEN_TTS_PREVIEW_TIMEOUT_SECONDS` (120 s),
при ошибке/тайм-ауте показывает ошибку вместо подмены
Piper. Синтез и прослушивание примера не обращаются к LLM и инструментам.
Для немедленного подтверждения после записи остаются сигнал и видимая анимация;
нейросинтез подтверждения не задерживает основной запрос.

## Измерение на текущем Mac через Linux Docker, 2026-10-17

CPU, 4 потока, модель 0.6B, фраза «Привет! Я Дельта. Чем могу помочь?»:

| Голос | Генерация | Длина аудио | RTF |
|---|---:|---:|---:|
| Qwen Serena | 31,67 s | 3,12 s | 10,15 |
| Piper Irina | 3,56 s | 2,97 s | 1,20 |

Один реальный прогон, не статистический нагрузочный тест; на хосте работали другие
контейнеры. Образцы и JSON: `.runtime/neural-samples/`. Повторение:
`scripts/benchmark_neural_voice.py` внутри нейрообраза с моделями и writable `/output`.
Качество звучания оценивается прослушиванием, а не одним временем генерации.
На локальной машине бюджет ответа установлен 45 s, чтобы можно было проверить
нейроголос; default для развёртывания остаётся 20 s. Быстрый диалог с этой моделью
нуждается в ускорении — поставляемый CUDA-профиль требует отдельной проверки на GPU.

Whisper small распознал образец Serena полностью: «Привет, я Дельта. Чем могу помочь?».
Это проверка содержания, не субъективной естественности голоса. Загрузка модели в
измеренном прогоне заняла 22,73 s; она выполняется один раз на процесс Core.

После финального перезапуска Core: `neural_ready=true`; реальный preview Ryan
«Задача добавлена.» вернул Qwen WAV за 21,76 s. Реальная цепочка Whisper → local
`devices.list` → явно выбранный Piper — 7,33 s, вызовов OpenRouter нет. Core/Tasks/DB
здоровы, Agent подключён, UI запущен на http://localhost:8081. Проверки: 188 backend,
6 frontend unit, 30 Chrome; после финальной правки playback повторены 16 voice-сценариев.
