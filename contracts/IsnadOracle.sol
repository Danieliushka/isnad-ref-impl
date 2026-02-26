// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IsnadOracle
 * @notice On-chain oracle for isnad agent trust scores.
 * @dev PoC for Agent Credit Network (ACN) on Base Sepolia.
 *      Scores are stored as basis points (0–10000) mapping to isnad float [0, 1.0].
 *      Only the authorized operator (Chainlink External Adapter) can update scores.
 */
contract IsnadOracle {
    // ─── Types ────────────────────────────────────────────────────

    struct TrustScore {
        uint256 score;            // 0–10000 basis points
        uint256 timestamp;        // block.timestamp of last update
        bytes32 attestationHash;  // SHA-256 of isnad TrustCertificate
        bool exists;
    }

    // ─── State ────────────────────────────────────────────────────

    address public owner;
    address public operator;

    mapping(address => TrustScore) private _scores;
    address[] private _agents;  // enumeration

    // ─── Events ───────────────────────────────────────────────────

    event TrustScoreUpdated(
        address indexed agent,
        uint256 score,
        uint256 timestamp,
        bytes32 attestationHash
    );

    event TrustScoreRevoked(address indexed agent, uint256 timestamp);
    event OperatorUpdated(address indexed oldOperator, address indexed newOperator);

    // ─── Modifiers ────────────────────────────────────────────────

    modifier onlyOwner() {
        require(msg.sender == owner, "IsnadOracle: caller is not owner");
        _;
    }

    modifier onlyOperator() {
        require(msg.sender == operator, "IsnadOracle: caller is not operator");
        _;
    }

    // ─── Constructor ──────────────────────────────────────────────

    constructor(address _operator) {
        owner = msg.sender;
        operator = _operator;
    }

    // ─── Operator Functions ───────────────────────────────────────

    /**
     * @notice Update trust score for an agent.
     * @param agent   The agent's Ethereum address.
     * @param score   Trust score in basis points (0–10000).
     * @param attestationHash  SHA-256 hash of the isnad TrustCertificate.
     */
    function updateTrustScore(
        address agent,
        uint256 score,
        bytes32 attestationHash
    ) external onlyOperator {
        require(score <= 10000, "IsnadOracle: score exceeds max");
        require(agent != address(0), "IsnadOracle: zero address");

        if (!_scores[agent].exists) {
            _agents.push(agent);
        }

        _scores[agent] = TrustScore({
            score: score,
            timestamp: block.timestamp,
            attestationHash: attestationHash,
            exists: true
        });

        emit TrustScoreUpdated(agent, score, block.timestamp, attestationHash);
    }

    /**
     * @notice Batch update trust scores.
     */
    function batchUpdateTrustScores(
        address[] calldata agents,
        uint256[] calldata scores,
        bytes32[] calldata attestationHashes
    ) external onlyOperator {
        require(
            agents.length == scores.length && scores.length == attestationHashes.length,
            "IsnadOracle: array length mismatch"
        );
        for (uint256 i = 0; i < agents.length; i++) {
            require(scores[i] <= 10000, "IsnadOracle: score exceeds max");
            require(agents[i] != address(0), "IsnadOracle: zero address");

            if (!_scores[agents[i]].exists) {
                _agents.push(agents[i]);
            }

            _scores[agents[i]] = TrustScore({
                score: scores[i],
                timestamp: block.timestamp,
                attestationHash: attestationHashes[i],
                exists: true
            });

            emit TrustScoreUpdated(agents[i], scores[i], block.timestamp, attestationHashes[i]);
        }
    }

    /**
     * @notice Revoke an agent's trust score (set to 0).
     */
    function revokeScore(address agent) external onlyOperator {
        require(_scores[agent].exists, "IsnadOracle: agent not found");

        _scores[agent].score = 0;
        _scores[agent].timestamp = block.timestamp;
        _scores[agent].attestationHash = bytes32(0);

        emit TrustScoreRevoked(agent, block.timestamp);
    }

    // ─── View Functions ───────────────────────────────────────────

    /**
     * @notice Get trust score for an agent.
     * @return score            Basis points (0–10000)
     * @return timestamp        Last update time
     * @return attestationHash  Hash of isnad certificate
     */
    function getTrustScore(address agent)
        external
        view
        returns (uint256 score, uint256 timestamp, bytes32 attestationHash)
    {
        TrustScore storage ts = _scores[agent];
        return (ts.score, ts.timestamp, ts.attestationHash);
    }

    /**
     * @notice Check if agent has a score on record.
     */
    function hasScore(address agent) external view returns (bool) {
        return _scores[agent].exists;
    }

    /**
     * @notice Get certification level string from score.
     * @dev Mirrors isnad CertificationLevel thresholds.
     */
    function getCertificationLevel(address agent) external view returns (string memory) {
        uint256 s = _scores[agent].score;
        if (s >= 9500) return "PLATINUM";
        if (s >= 8000) return "GOLD";
        if (s >= 6000) return "SILVER";
        if (s >= 4000) return "BRONZE";
        return "NONE";
    }

    /**
     * @notice Total number of scored agents.
     */
    function agentCount() external view returns (uint256) {
        return _agents.length;
    }

    // ─── Admin ────────────────────────────────────────────────────

    function setOperator(address _operator) external onlyOwner {
        emit OperatorUpdated(operator, _operator);
        operator = _operator;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "IsnadOracle: zero address");
        owner = newOwner;
    }
}
