// netlify/functions/trigger.js
// Variables d'env Netlify requises : GITHUB_TOKEN, GITHUB_REPO

exports.handler = async function (event) {
  const headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
  };

  if (event.httpMethod === "OPTIONS") return { statusCode: 200, headers, body: "" };
  if (event.httpMethod !== "POST") return { statusCode: 405, headers, body: JSON.stringify({ error: "Method not allowed" }) };

  const token = process.env.GITHUB_TOKEN;
  const repo  = process.env.GITHUB_REPO;
  if (!token || !repo) return { statusCode: 500, headers, body: JSON.stringify({ error: "GITHUB_TOKEN ou GITHUB_REPO manquant" }) };

  let body;
  try { body = JSON.parse(event.body || "{}"); }
  catch { return { statusCode: 400, headers, body: JSON.stringify({ error: "JSON invalide" }) }; }

  const prompt     = (body.prompt      || "").trim();
  const publishNow = body.publish_now  === true ? "true" : "false";
  const dryRun     = body.dry_run      === true ? "true" : "false";

  const url = `https://api.github.com/repos/${repo}/actions/workflows/daily.yml/dispatches`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs: { prompt, publish_now: publishNow, dry_run: dryRun } }),
    });

    if (response.status === 204) {
      return { statusCode: 200, headers, body: JSON.stringify({ success: true, message: "Pipeline lancé !" }) };
    } else {
      const text = await response.text();
      return { statusCode: response.status, headers, body: JSON.stringify({ error: `GitHub API ${response.status}`, detail: text }) };
    }
  } catch (err) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: "Erreur réseau", detail: err.message }) };
  }
};
