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
 *    the percentage is healthy. Qualitative wording is taken only from the
 *    dashboard's verified attention state; a raw frontend number never invents
 *    its own threshold. Unknown states therefore get neutral questions. A
 *    metric at zero still avoids questions about items that do not exist.
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
  completion_pct(card, scope) {
    const where = scopePhrase(scope);
    const shown = describeValue(card.value, "%");
    const options = [];
    // The attention item is emitted by the dashboard's configured backend
    // threshold. Absence of that item is not treated as proof that a raw
    // percentage is high or low.
    if (card.attention) {
      options.push({
        id: "why-low",
        label: "Why does completion need attention?",
        question: `Sprint Completion for ${where} is ${shown} and is flagged by the dashboard attention rules. What is driving the current completion rate? Break down work still outside Done by status category and issue type.`,
      });
    } else {
      options.push({
        id: "drivers",
        label: "What is driving completion?",
        question: `Sprint Completion for ${where} is ${shown}. What is driving the current completion rate, and is any remaining work still at risk?`,
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

  active_work(card, scope) {
    const where = scopePhrase(scope);
    const shown = describeValue(card.value);
    return [
      {
        id: "attention",
        label: "Which open items need attention?",
        question: `Open Work for ${where} is currently ${shown}. Which open items need the most attention? Rank them using verified priority and age.`,
      },
      {
        id: "distribution",
        label: "How is open work distributed?",
        question: `Open Work for ${where} is currently ${shown}. Show how it is distributed by status category, issue type and priority.`,
      },
      {
        id: "prioritise",
        label: "What should be prioritised next?",
        question: `Open Work for ${where} is currently ${shown}. What should the squad prioritise next, based on the available priority, age and impediment evidence?`,
      },
    ];
  },

  impeded_work(card, scope) {
    const where = scopePhrase(scope);
    const count = numeric(card.value) ?? 0;
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
        question: `Active Blockers for ${where} is currently ${describeValue(card.value)} tickets based on the verified Impeded status. Which should be unblocked first? Rank them by priority and age, and explain the ranking.`,
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

  open_bugs(card, scope) {
    const where = scopePhrase(scope);
    const shown = describeValue(card.value);
    return [
      {
        id: "prioritise",
        label: "Which bugs should be prioritised?",
        question: `Open Bugs for ${where} is currently ${shown}. Which open bugs should be prioritised using their verified priority and age?`,
      },
      {
        id: "priority-distribution",
        label: "How are bugs distributed by priority?",
        question: `Open Bugs for ${where} is currently ${shown}. Show how the open bugs are distributed by priority.`,
      },
      {
        id: "delivery-risk",
        label: "Are bugs creating delivery risk?",
        question: `Open Bugs for ${where} is currently ${shown}. Are any of these bugs contributing to a verified delivery attention signal?`,
      },
    ];
  },

  delivery_risk(card, scope) {
    const where = scopePhrase(scope);
    const status = String(card.value ?? "").toLowerCase();
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
        question: `The delivery-risk status for ${where} is ${describeValue(card.value)}. Which signals are closest to crossing an attention threshold, and how far away are they?`,
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
  if (builder) return builder(card, scope);
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
