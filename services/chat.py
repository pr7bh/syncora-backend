from services.rag import search_transcript
from services.llm import generate_response


def format_time(seconds):

    minutes = int(seconds // 60)
    seconds = int(seconds % 60)

    return f"{minutes:02d}:{seconds:02d}"


def ask_question(meeting_id: str, question: str):

    chunks = search_transcript(
        meeting_id,
        question
    )

    context = "\n".join(
        f"[{format_time(chunk['start'])} - "
        f"{format_time(chunk['end'])}] "
        f"{chunk['text']}"
        for chunk in chunks
    )

    prompt = f"""
        You are Syncora, an intelligent AI assistant that helps users understand
        their meeting while also being able to answer general questions.

        Retrieved meeting transcript:
        --------------------------------
        {context}
        --------------------------------

        User question:
        {question}

        Follow these rules:

        1. First determine what type of question the user is asking.

        2. If the question is about the meeting:
        - Use the retrieved meeting transcript as the primary source.
        - Combine information from multiple retrieved chunks when necessary.
        - Do not invent meeting-specific information.
        - If the information cannot be found, clearly say so.

        3. If the question is a general knowledge question:
        - Answer using your general knowledge.
        - Do not refuse just because the topic is not present in the meeting.

        4. If the question combines both:
        - Use the transcript for meeting-specific information.
        - Use general knowledge for other concepts.

        5. Never fabricate meeting-specific facts.

        6. Include timestamps when relevant.

        7. Answer the actual question directly.

        8. Keep answers concise, natural, and conversational.

        Now answer the user's question.
        """

    return generate_response(prompt)