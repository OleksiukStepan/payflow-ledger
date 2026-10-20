"use strict";

// Every value from the API reaches the page through textContent only: merchant names come from webhooks.
const STATUSES = new Set(["pending", "captured", "reversed"]);
const SCENARIOS = {
  acc_1: "PayFlow's happy_path.json delivered in order: a funding, four authorizations, captures, a reversal and a refund. Expected: 585.00 available, 15.00 on hold.",
  acc_3: "scenarios/edge_cases.json delivered out of order: events before the first funding, captures above and below the hold, a partial reversal, a capture racing a reversal, a re-sent refund, an unknown event type and a EUR authorization. Expected: 555.00 available, 0.00 on hold.",
};
const byId = (id) => document.getElementById(id);
let latestRequest = 0;

function cell(text, className = "") {
  const element = document.createElement("td");
  element.textContent = text;
  element.className = className;
  return element;
}

function row(item, accountCurrency) {
  const element = document.createElement("tr");
  const pill = document.createElement("span");
  pill.className = `pill ${STATUSES.has(item.status) ? item.status : ""}`;
  pill.textContent = item.status;
  const status = cell("");
  status.append(pill);
  const money = (amount) => (amount === null ? "unknown" : `${amount} ${item.currency}`);
  element.append(
    cell(item.authorization_id, "mono"),
    cell(item.merchant ?? "unknown yet", item.merchant ? "" : "muted"),
    status,
    cell(money(item.authorized_amount), "num"),
    cell(money(item.captured_amount), "num"),
    cell(money(item.refunded_amount), "num"),
    cell(item.created_at ? item.created_at.replace("T", " ").replace("Z", " UTC") : "unknown yet", "muted"),
  );
  if (item.currency !== accountCurrency) element.className = "foreign";
  return element;
}

function show(sectionId) {
  for (const id of ["account", "empty", "error"]) byId(id).hidden = id !== sectionId;
}

async function load(accountId) {
  // A slower answer to an older request must not overwrite a newer one.
  const request = ++latestRequest;
  const path = `/accounts/${encodeURIComponent(accountId)}`;
  try {
    const [balance, transactions] = await Promise.all(
      [`${path}/balance`, `${path}/transactions`].map(async (url) => {
        const response = await fetch(url);
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`API answered ${response.status}`);
        return response.json();
      }),
    );
    if (request !== latestRequest) return;
    if (balance === null) {
      byId("empty-text").textContent = `No account.funded event has arrived for "${accountId}" yet.`;
      show("empty");
    } else {
      byId("available").textContent = `${balance.available} ${balance.currency}`;
      byId("pending").textContent = `${balance.pending} ${balance.currency}`;
      byId("rows").replaceChildren(...transactions.items.map((item) => row(item, balance.currency)));
      show("account");
    }
    byId("updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    if (request !== latestRequest) return;
    byId("error").textContent = `Could not load the account: ${error.message}`;
    show("error");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const select = byId("scenario");
  const input = byId("account-id");
  const account = () => select.value || input.value.trim();

  function choose(accountId) {
    select.value = Object.hasOwn(SCENARIOS, accountId) ? accountId : "";
    input.hidden = select.value !== "";
    if (input.hidden) input.value = "";
    else if (accountId) input.value = accountId;
    byId("scenario-note").textContent = SCENARIOS[select.value] ?? "Any account id that received events, for example from your own event files.";
    history.replaceState(null, "", account() ? `#${encodeURIComponent(account())}` : location.pathname);
    if (account()) load(account());
    else show("");
  }

  select.addEventListener("change", () => choose(select.value));
  byId("account-form").addEventListener("submit", (event) => {
    event.preventDefault();
    choose(account());
  });
  setInterval(() => {
    if (byId("auto-refresh").checked && document.visibilityState === "visible" && account()) load(account());
  }, 3000);

  byId("send-command").textContent = `python3 PayFlowEventsSender.py happy_path.json --url ${location.origin}/webhooks`;
  let fromLink = "acc_1";
  try {
    if (location.hash.length > 1) fromLink = decodeURIComponent(location.hash.slice(1));
  } catch {
    // A malformed link keeps the default scenario instead of breaking the page.
  }
  choose(fromLink);
});
