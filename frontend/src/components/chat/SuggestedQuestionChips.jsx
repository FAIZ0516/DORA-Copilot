import { ChevronRight, Sparkles } from "lucide-react";

export default function SuggestedQuestionChips({ questions = [], onSuggestionClick, label = "Suggested questions" }) {
  if (!questions.length) return null;
  return (
    <section className="suggested-question-section" aria-label={label}>
      <p><Sparkles aria-hidden="true" /> {label}</p>
      <div className="suggested-question-chips">
        {questions.slice(0, 5).map((question) => (
          <button type="button" key={question} onClick={() => onSuggestionClick(question)}><span>{question}</span><ChevronRight aria-hidden="true" /></button>
        ))}
      </div>
    </section>
  );
}
