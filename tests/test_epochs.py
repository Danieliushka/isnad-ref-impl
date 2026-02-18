"""Tests for isnad.epochs — multi-speed trust epochs."""

import time
import math
import pytest

from isnad.epochs import (
    EpochPolicy,
    EpochManager,
    PAYMENT_EPOCH,
    REPUTATION_EPOCH,
    IDENTITY_EPOCH,
)


# ── EpochPolicy dataclass tests ─────────────────────────────────────


class TestEpochPolicy:
    def test_valid_creation(self):
        p = EpochPolicy("test", 60, "linear", 0.5, 3, "time")
        assert p.domain == "test"
        assert p.epoch_duration_seconds == 60

    def test_invalid_decay_curve(self):
        with pytest.raises(ValueError, match="Invalid decay_curve"):
            EpochPolicy("x", 60, "cubic", 0.5, 3)

    def test_invalid_decay_rate_high(self):
        with pytest.raises(ValueError, match="decay_rate"):
            EpochPolicy("x", 60, "linear", 1.5, 3)

    def test_invalid_decay_rate_negative(self):
        with pytest.raises(ValueError, match="decay_rate"):
            EpochPolicy("x", 60, "linear", -0.1, 3)

    def test_invalid_boundary_condition(self):
        with pytest.raises(ValueError, match="Invalid boundary_condition"):
            EpochPolicy("x", 60, "linear", 0.5, 3, "random")

    def test_invalid_duration(self):
        with pytest.raises(ValueError, match="positive"):
            EpochPolicy("x", 0, "linear", 0.5, 3)


# ── Default policies ────────────────────────────────────────────────


class TestDefaults:
    def test_payment_epoch(self):
        assert PAYMENT_EPOCH.domain == "payment"
        assert PAYMENT_EPOCH.epoch_duration_seconds == 30
        assert PAYMENT_EPOCH.decay_curve == "exponential"

    def test_reputation_epoch(self):
        assert REPUTATION_EPOCH.epoch_duration_seconds == 7 * 24 * 3600

    def test_identity_epoch(self):
        assert IDENTITY_EPOCH.decay_curve == "step"
        assert IDENTITY_EPOCH.epoch_duration_seconds == 30 * 24 * 3600


# ── EpochManager tests ──────────────────────────────────────────────


class TestEpochManager:
    def setup_method(self):
        self.mgr = EpochManager()

    def test_register_and_get_epoch(self):
        policy = EpochPolicy("fast", 1, "linear", 0.1, 1)
        self.mgr.register_policy(policy)
        epoch = self.mgr.get_current_epoch("fast")
        assert epoch >= 0

    def test_unregistered_domain_raises(self):
        with pytest.raises(KeyError, match="No policy"):
            self.mgr.get_current_epoch("nonexistent")

    def test_compute_decay_linear(self):
        self.mgr.register_policy(EpochPolicy("d", 60, "linear", 0.2, 1))
        assert self.mgr.compute_decay("d", 0) == 1.0
        assert self.mgr.compute_decay("d", 1) == pytest.approx(0.8)
        assert self.mgr.compute_decay("d", 5) == pytest.approx(0.0)
        # Beyond full decay — clamped to 0
        assert self.mgr.compute_decay("d", 10) == 0.0

    def test_compute_decay_exponential(self):
        self.mgr.register_policy(EpochPolicy("d", 60, "exponential", 0.3, 1))
        assert self.mgr.compute_decay("d", 0) == 1.0
        assert self.mgr.compute_decay("d", 1) == pytest.approx(0.7)
        assert self.mgr.compute_decay("d", 3) == pytest.approx(0.7 ** 3)

    def test_compute_decay_step(self):
        self.mgr.register_policy(EpochPolicy("d", 60, "step", 0.05, 1))
        assert self.mgr.compute_decay("d", 0) == 1.0
        assert self.mgr.compute_decay("d", 1) == pytest.approx(0.95)
        assert self.mgr.compute_decay("d", 20) == pytest.approx(0.0)

    def test_compute_decay_negative_epochs(self):
        self.mgr.register_policy(EpochPolicy("d", 60, "linear", 0.5, 1))
        assert self.mgr.compute_decay("d", -5) == 1.0

    def test_should_rotate_time_based(self):
        # 1-second epoch — register and immediately check
        self.mgr.register_policy(EpochPolicy("fast", 1, "linear", 0.1, 1))
        # Just registered, might not have rotated yet
        time.sleep(1.1)
        assert self.mgr.should_rotate("fast") is True

    def test_should_rotate_event_count(self):
        self.mgr.register_policy(
            EpochPolicy("ev", 9999, "linear", 0.1, 3, "event_count")
        )
        assert self.mgr.should_rotate("ev") is False
        self.mgr.record_event("ev")
        self.mgr.record_event("ev")
        assert self.mgr.should_rotate("ev") is False
        self.mgr.record_event("ev")
        assert self.mgr.should_rotate("ev") is True

    def test_should_rotate_semantic(self):
        self.mgr.register_policy(
            EpochPolicy("sem", 1, "linear", 0.1, 1, "semantic")
        )
        time.sleep(1.1)
        # Semantic never auto-rotates
        assert self.mgr.should_rotate("sem") is False

    def test_cross_domain_same(self):
        self.mgr.register_policy(PAYMENT_EPOCH)
        assert self.mgr.cross_domain_bridge("payment", "payment") == 1.0

    def test_cross_domain_fast_to_slow(self):
        self.mgr.register_policy(PAYMENT_EPOCH)
        self.mgr.register_policy(IDENTITY_EPOCH)
        multiplier = self.mgr.cross_domain_bridge("payment", "identity")
        # 30 / (30*24*3600) ≈ very small
        assert 0.0 < multiplier < 0.01

    def test_cross_domain_slow_to_fast(self):
        self.mgr.register_policy(PAYMENT_EPOCH)
        self.mgr.register_policy(IDENTITY_EPOCH)
        # Symmetric
        m1 = self.mgr.cross_domain_bridge("payment", "identity")
        m2 = self.mgr.cross_domain_bridge("identity", "payment")
        assert m1 == pytest.approx(m2)

    def test_cross_domain_reputation_to_identity(self):
        self.mgr.register_policy(REPUTATION_EPOCH)
        self.mgr.register_policy(IDENTITY_EPOCH)
        m = self.mgr.cross_domain_bridge("reputation", "identity")
        expected = (7 * 24 * 3600) / (30 * 24 * 3600)
        assert m == pytest.approx(expected)

    def test_reregister_resets_clock(self):
        policy = EpochPolicy("d", 9999, "linear", 0.1, 1)
        self.mgr.register_policy(policy)
        t1 = self.mgr._start_times["d"]
        time.sleep(0.05)
        self.mgr.register_policy(policy)
        t2 = self.mgr._start_times["d"]
        assert t2 > t1
