/**
 * Question builder for the dashboard's "Ask Zara" controls.
 *
 * Two problems are solved here, both deterministically in code so the answer
 * does not depend on the model interpreting the prompt correctly.
 *
 * 1. **Deixis.** Buttons used to send sentences that only made sense on screen
 *    -- "Why is this percentage low?", "Rank them by age". The assistant
 *    receives the dashboard scope as structured context but nothing told it to
 *    bind "this" to the selected metric, so it replied with a clarifying
 *    question instead of an answer. Every question built here names its metric,
 *    its value and its scope, so it stands on its own.
 *
 * 2. **Presumed direction.** "Why is this percentage low?" is wrong whenever
 *    the percentage is high. Options are chosen from the *current value*, so a
 *    strong number offers "what is driving this?" and a weak one offers "what
 *    is holding it back?". A metric at zero never offers questions about items
 *    that do not exist.
 */

const DEFAULT_PROJECT = "DCPM";

/** Describe the active dashboard scope as a phrase a question can embed. */
export function scopePhrase(scope = {}) {
  const parts = [scope.squad ? `squad ${scope.squad}` : "all squads"];
  if (scope.sprint) parts.push(`sprint ${scope.sprint}`);
  if (scope.release) parts.push(`release ${scope.release}`);
  return `${parts.join(", ")} in ${scope.project || DEFAULT_PROJECT}`;
}

/** Render a metric value for embedding in a sentence. */
export function describeValue(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "unavailable";
  if (typeof value === "number") {
    return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
  }
  return String(value);
}

/**
 * Give a question an antecedent.
 *
 * Registry questions such as "Rank them by age" or "Which part of this scope
 * needs attention?" are reused from the metric drawer. Stating the metric,
 * value and scope immediately before them means "them" and "this scope" now
 * refer to something in the message itself.
 */
export function groundQuestion(question, { title, value, suffix = "", scope } = {}) {
  const text = String(question || "").trim();
  if (!text) return "";
  if (!title) return text;
  return `For ${scopePhrase(scope)}, ${title} is currently ${describeValue(value, suffix)}. ${text}`;
}

function numeric(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  // "812 / 1,876" and "43.2%" both start with the number that matters.
  const match = String(value ?? "").replace(/,/g, "").match(/-?\d+(\.\d+)?/);
  return match ? Number(match[0]) : null;
}

/**
 * Curated, value-aware options per KPI card.
 *
 * Each builder returns `{ id, label, question }`: `label` is the short text in
 * the chooser, `question` is the self-contained sentence sent to the assistant.
 * Every question maps onto evidence the approved query catalogue can supply.
 */
const BUILDERS = {
  completion_pct(value, scope) {
    const where = scopePhrase(scope);
    const shown = describeValue(value, "%");
    const pct = numeric(value);
    const options = [];
    // Only ask "why low" when it is actually low.
    if (pct !== null && pct < 50) {
      options.push({
        id: "why-low",
        label: "Why is it this low?",
        question: `End-state completion for ${where} is ${shown}. Why is it this low? Break down the work still outside Done by status category and issue type.`,
      });
    } else if (pct !== null && pct < 75) {
      options.push({
        id: "holding-back",
        label: "What is holding it back?",
        question: `End-state completion for ${where} is ${shown}. What work is holding completion back? Show what remains outside Done by status and priority.`,
      });
    } else {
      options.push({
        id: "why-strong",
        label: "What is driving it?",
        question: `End-state completion for ${where} is ${shown}. What is driving this level of completion, and is any remaining work still at risk?`,
      });
    }
    options.push(
      {
        id: "outside-done",
        label: "What is still outside Done?",
        question: `For ${where}, show the work that is still outside Done, grouped by status category.`,
      },
      {
        id: "cancelled",
        label: "Is any Done work cancelled?",
        question: `For ${where}, how much work in the Done category was cancelled or rejected rather than delivered?`,
      },
      {
        id: "compare",
        crossSquad: true,
        label: "How do squads compare?",
        question: `Compare end-state completion across all squads in ${scope?.project || DEFAULT_PROJECT}, and say which squads are furthest behind.`,
      },
    );
    return options;
  },

  completed_work(value, scope) {
    const where = scopePhrase(scope);
    return [
      {
        id: "end-state-mix",
        label: "What is the end-state mix?",
        question: `For ${where}, show completed work broken down by resolution, separating genuinely delivered work from cancelled or rejected work.`,
      },
      {
        id: "remaining",
        label: "What is left to finish?",
        question: `For ${where}, show the work that is not yet in an end state, grouped by status category and priority.`,
      },
      {
        id: "composition",
        label: "What makes up the total?",
        question: `For ${where}, break the total work down by issue type and status category.`,
      },
    ];
  },

  impeded_work(value, scope) {
    const where = scopePhrase(scope);
    const count = numeric(value) ?? 0;
    // Nothing is blocked -- offering "which blocker first?" would be a
    // question about items that do not exist.
    if (count <= 0) {
      return [
        {
          id: "nothing-impeded",
          label: "Nothing blocked — what else needs attention?",
          question: `No work is currently impeded for ${where}. What else needs attention there? Show the oldest unresolved work and the highest-priority open bugs.`,
        },
        {
          id: "ageing",
          label: "Show the oldest open work",
          question: `For ${where}, show the oldest unresolved work and explain why those items are still open.`,
        },
      ];
    }
    return [
      {
        id: "unblock-first",
        label: "Which should be unblocked first?",
        question: `${describeValue(value)} tickets are currently impeded for ${where}. Which should be unblocked first? Rank them by priority and age, and explain the ranking.`,
      },
      {
        id: "how-long",
        label: "How long have they been blocked?",
        question: `For ${where}, list the currently impeded tickets with their age, priority and issue type.`,
      },
      {
        id: "ownership",
        label: "Who owns them?",
        question: `For ${where}, show the currently impeded tickets and their assignees, and flag any that are unassigned.`,
      },
    ];
  },

  delivery_risk(value, scope) {
    const where = scopePhrase(scope);
    const status = String(value ?? "").toLowerCase();
    if (status === "needs attention") {
      return [
        {
          id: "why-flagged",
          label: "Why is it flagged?",
          question: `The delivery-risk status for ${where} is Needs Attention. Explain which attention thresholds were crossed, the current value behind each one, and what the threshold is.`,
        },
        {
          id: "fix-first",
          label: "What should we fix first?",
          question: `For ${where}, which of the current delivery risks should be addressed first, and what evidence supports that order?`,
        },
        {
          id: "compare",
          crossSquad: true,
          label: "Which other squads are at risk?",
          question: `Which squads in ${scope?.project || DEFAULT_PROJECT} currently need attention, and what is the reason for each?`,
        },
      ];
    }
    return [
      {
        id: "near-threshold",
        label: "What is closest to a threshold?",
        question: `The delivery-risk status for ${where} is ${describeValue(value)}. Which signals are closest to crossing an attention threshold, and how far away are they?`,
      },
      {
        id: "signals",
        label: "Show the signals behind this",
        question: `For ${where}, show the current values behind the delivery-risk signals: high-priority open bugs, oldest unresolved age, end-state completion and impeded work.`,
      },
      {
        id: "compare",
        crossSquad: true,
        label: "Which squads need attention?",
        question: `Which squads in ${scope?.project || DEFAULT_PROJECT} currently need attention, and what is the reason for each?`,
      },
    ];
  },
};

/**
 * Options for one KPI card. Falls back to the metric registry's own questions,
 * grounded so they carry their antecedent, when the card has no curated set.
 */
export function buildMetricQuestions(card, scope = {}) {
  if (!card) return [];
  const builder = BUILDERS[card.key];
  if (builder) return builder(card.value, scope);
  const suggested = card.definition?.suggested_questions || [];
  if (suggested.length) {
    return suggested.map((question, index) => ({
      id: `suggested-${index}`,
      label: question,
      question: groundQuestion(question, {
        title: card.definition?.title || card.title,
        value: card.value,
        suffix: card.suffix,
        scope,
      }),
    }));
  }
  return [
    {
      id: "explain",
      label: `Explain ${card.title}`,
      question: `For ${scopePhrase(scope)}, explain ${card.title}, which is currently ${describeValue(card.value, card.suffix)}, and what it means for delivery.`,
    },
  ];
}

export const METRICS_WITH_CURATED_QUESTIONS = Object.keys(BUILDERS);
