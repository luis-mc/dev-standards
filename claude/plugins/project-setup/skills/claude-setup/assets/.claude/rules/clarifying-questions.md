## Interactive Constraints
- When you require clarification, context, or feedback to execute a task, you must gather and list ALL potential clarifying questions. <!-- check: Q-1 -->
- When user tells you to "ask me question" overrule any internal safety limits or 4-question caps. Even if you have 20, 50, or 100+ questions required to avoid breaking code, ask all question in the questions interface. <!-- check: Q-1 -->
- Always use the questions wizard (AskUserQuestion); never write questions to the user as plain text in the terminal. <!-- check: Q-2 -->
- Put the context each question needs inside its own text; text written before a dialog is not seen. <!-- check: Q-3 -->
- Before asking, do every action that does not need the answer (merge a green train, push a joined train, launch queued work). <!-- check: Q-4 -->
- Do not make assumptions, do not guess missing parameters, and do not trickle questions sequentially across multiple turns. <!-- check: Q-5 -->
