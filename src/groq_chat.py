from __future__ import annotations

from groq import Groq


SYSTEM_PROMPT_RU = """Ты - Олег, — администратор салона красоты "{salon_name}". Адрес салона: {address}.
Часы работы: с 10 до 20, кроме субботы. Твоя задача: кратко и вежливо консультировать клиента по услугам, ценам, длительности, уходу и подготовке.
Если клиент хочет записаться, попроси: услугу, дату, время, имя и телефон. Не выдумывай цены и другую информацию — используй только список услуг ниже.
Если информации не хватает, задавай уточняющие вопросы. 
ВАЖНО: Если клиент хочет записаться (говорит "да", "запиши", "хочу записаться", "как записаться"), 
попроси его использовать команду /book или напиши: "Чтобы записаться, нажмите /book".
Отвечай по-русски, как человек, короткими сообщениями. Отвечай только на вопросы, связанные с салоном. Мягко возвращай к теме салона.
Список услуг:
{services_text}
"""


class GroqConsultant:
    def __init__(self, api_key: str, model: str, salon_name: str, services_text: str, address: str) -> None:
        self._client = Groq(api_key=api_key)
        self._model = model
        self._system = SYSTEM_PROMPT_RU.format(
            salon_name=salon_name,
            services_text=services_text,
            address=address,
        )

    def reply(self, user_text: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system},
                {"role": "user", "content": user_text},
            ],
            temperature=0.4,
            max_tokens=350,
        )
        return (resp.choices[0].message.content or "").strip()

