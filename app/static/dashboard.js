"use strict";

// Every value from the API reaches the page through textContent only: merchant names come from webhooks.
const STATUSES = new Set(["pending", "captured", "reversed"]);
const REFRESH_MS = 3000;

const byId = (id) => document.getElementById(id);

// Money stays in integer cents: "125.50" -> 12550, never a float.
function toCents(amount) {
  const negative = amount.startsWith("-");
  const [whole, fraction = "0"] = amount.replace("-", "").split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0").slice(0, 2));
  return negative ? -cents : cents;
}

function formatCents(cents) {
  const sign = cents < 0 ? "-" : "";
  const absolute = Math.abs(cents);
  return `${sign}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, "0")}`;
}

function cell(text, className) {
  const element = document.createElement("td");
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function statusCell(status) {
  const element = document.createElement("td");
  const pill = document.createElement("span");
  pill.className = `pill ${STATUSES.has(status) ? status : "unknown"}`;
  pill.textContent = status;
  element.append(pill);
  return element;
}

function renderRows(items, currency) {
  const rows = items.map((item) => {
    const row = document.createElement("tr");
    const foreign = item.currency !== currency;
    row.append(
      cell(item.authorization_id, "mono"),
      cell(item.merchant ?? "unknown yet", item.merchant ? "" : "muted"),
      statusCell(item.status),
      cell(item.authorized_amount === null ? "unknown" : `${item.authorized_amount} ${item.currency}`, "num"),
      cell(`${item.captured_amount} ${item.currency}`, "num"),
      cell(`${item.refunded_amount} ${item.currency}`, "num"),
      cell(item.created_at ? item.created_at.replace("T", " ").replace("Z", " UTC") : "unknown yet", "muted"),
    );
    if (foreign) {
      row.className = "foreign";
      row.title = `In ${item.currency}, not the account currency: left out of the balance`;
    }
    return row;
  });
  byId("rows").replaceChildren(...rows);
}

function renderAccount(balance, items) {
  const inCurrency = items.filter((item) => item.currency === balance.currency);
  const captured = inCurrency.reduce((sum, item) => sum + toCents(item.captured_amount), 0);
  const refunded = inCurrency.reduce((sum, item) => sum + toCents(item.refunded_amount), 0);
  const available = toCents(balance.available);
  const pending = toCents(balance.pending);
  const funded = available + pending + captured - refunded;

  byId("available").textContent = balance.available;
  byId("currency").textContent = balance.currency;
  byId("pending").textContent = balance.pending;
  byId("captured").textContent = formatCents(captured);
  byId("refunded").textContent = formatCents(refunded);
  byId("formula").textContent =
    `${formatCents(funded)} funded − ${balance.pending} pending − ${formatCents(captured)} captured + ` +
    `${formatCents(refunded)} refunded = ${balance.available} available`;
  renderRows(items, balance.currency);
}

function showOnly(sectionId) {
  for (const id of ["account", "empty", "error"]) byId(id).hidden = id !== sectionId;
}

async function load(accountId) {
  const path = `/accounts/${encodeURIComponent(accountId)}`;
  try {
    const [balanceResponse, transactionsResponse] = await Promise.all([
      fetch(`${path}/balance`),
      fetch(`${path}/transactions`),
    ]);
    if (balanceResponse.status === 404) {
      byId("empty-text").textContent = `No account.funded event has arrived for "${accountId}" yet.`;
      showOnly("empty");
    } else if (!balanceResponse.ok || !transactionsResponse.ok) {
      throw new Error(`API answered ${balanceResponse.status} / ${transactionsResponse.status}`);
    } else {
      renderAccount(await balanceResponse.json(), (await transactionsResponse.json()).items);
      showOnly("account");
    }
    byId("updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    byId("error").textContent = `Could not load the account: ${error.message}`;
    showOnly("error");
  }
}

function currentAccount() {
  return byId("account-id").value.trim();
}

document.addEventListener("DOMContentLoaded", () => {
  const fromHash = decodeURIComponent(location.hash.slice(1));
  if (fromHash) byId("account-id").value = fromHash;

  byId("account-form").addEventListener("submit", (event) => {
    event.preventDefault();
    history.replaceState(null, "", `#${encodeURIComponent(currentAccount())}`);
    load(currentAccount());
  });

  setInterval(() => {
    if (byId("auto-refresh").checked && document.visibilityState === "visible" && currentAccount()) {
      load(currentAccount());
    }
  }, REFRESH_MS);

  load(currentAccount());
});
