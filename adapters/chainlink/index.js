/**
 * Isnad Chainlink External Adapter
 *
 * Bridges off-chain isnad trust scores to Chainlink oracle requests.
 * Returns scores as uint256 basis points (0–10000).
 *
 * ENV:
 *   ISNAD_API_URL  — isnad API base URL (default: http://localhost:8000)
 *   PORT           — server port (default: 8080)
 */

const express = require("express");
const axios = require("axios");

const app = express();
app.use(express.json());

const ISNAD_API_URL = process.env.ISNAD_API_URL || "http://localhost:8000";
const PORT = process.env.PORT || 8080;

/**
 * Convert isnad float score [0, 1] to basis points [0, 10000].
 */
function toBasisPoints(score) {
  return Math.round(Math.min(Math.max(score, 0), 1) * 10000);
}

/**
 * Main adapter handler — Chainlink-compatible request/response.
 *
 * Input:  { id, data: { agentAddress } }
 * Output: { jobRunID, data: { result, score, attestationHash }, statusCode }
 */
async function handleRequest(input) {
  const jobRunID = input.id || "1";
  const agentAddress = input.data?.agentAddress;

  if (!agentAddress) {
    return {
      jobRunID,
      status: "errored",
      error: "Missing agentAddress in request data",
      statusCode: 400,
    };
  }

  try {
    // Call isnad API to get trust score for this agent
    const response = await axios.get(
      `${ISNAD_API_URL}/v1/trust-score/${agentAddress}`,
      { timeout: 10000 }
    );

    const { trust_score, attestation_hash } = response.data;
    const scoreBps = toBasisPoints(trust_score);

    return {
      jobRunID,
      data: {
        result: scoreBps,
        score: scoreBps,
        trustScoreFloat: trust_score,
        attestationHash: attestation_hash || "0x" + "0".repeat(64),
      },
      statusCode: 200,
    };
  } catch (error) {
    const msg = error.response?.data?.error || error.message;
    console.error(`[isnad-adapter] Error for ${agentAddress}: ${msg}`);

    return {
      jobRunID,
      status: "errored",
      error: msg,
      statusCode: 500,
    };
  }
}

// ─── Routes ──────────────────────────────────────────────────────

app.post("/trust-score", async (req, res) => {
  const result = await handleRequest(req.body);
  res.status(result.statusCode).json(result);
});

// Health check
app.get("/health", (_req, res) => {
  res.json({ status: "ok", adapter: "isnad-chainlink", version: "0.1.0" });
});

// ─── Start ───────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`isnad Chainlink adapter listening on port ${PORT}`);
  console.log(`isnad API: ${ISNAD_API_URL}`);
});

module.exports = { handleRequest, toBasisPoints };
