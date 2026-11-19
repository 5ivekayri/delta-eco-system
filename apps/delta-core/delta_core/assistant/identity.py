"""Product identity policy; common direct questions do not require inference."""
import re

IDENTITY_REPLY = 'Извините не могу ответить на данный вопрос.'
IDENTITY_POLICY = (
    'When asked about your underlying model, LLM, model provider, developer or creator, '
    f'reply with exactly: {IDENTITY_REPLY} '
    'Do not name or guess companies, creators, model names or versions. '
    'This rule concerns your own identity, not general questions about AI models. '
)


def identity_question(message: str) -> bool:
    text = ' '.join(message.casefold().replace('ё', 'е').split())
    patterns = (
        r'\bкто (?:тебя|вас) (?:создал|разработал|обучил|сделал)',
        r'\bкто (?:твой|ваш) (?:создатель|разработчик)',
        r'\b(?:твой|твоей|твоя|твою|ваш|ваша|вашей) (?:базов\w+ |языков\w+ )?(?:модел\w*|llm|ллм|разработчик\w*|создател\w*)',
        r'\b(?:модел\w*|llm|ллм|нейросет\w*)\b.{0,40}\b(?:в основе (?:тебя|вас)|ты (?:работаешь|используешь|являешься)|используется в тебе)\b',
        r'\b(?:какая|какой) у (?:тебя|вас) (?:модел\w*|llm|ллм|нейросет\w*)',
        r'\b(?:какая|какой) (?:ты|вы) (?:модел\w*|llm|ллм|нейросет\w*)',
        r'\b(?:ты|тебя|вы)\b.{0,55}\b(?:какой|какая|какая же|какую) (?:модел\w*|llm|ллм|нейросет\w*)',
        r'\bна (?:чем|чьей модели) ты (?:работаешь|основан\w*)',
        r'\b(?:ты|вы) (?:это )?(?:chatgpt|gpt[ -]?\d*|qwen|claude|llama|nemotron)\b',
        r'\bwho (?:created|made|developed|trained) you\b',
        r'\b(?:your (?:underlying |base |language )?(?:model|llm|creator|developer)|who is your creator)\b',
        r'\b(?:what|which) (?:language |underlying |base )?(?:model|llm) (?:are you|powers you|do you use)\b',
    )
    return any(re.search(pattern, text) for pattern in patterns)
