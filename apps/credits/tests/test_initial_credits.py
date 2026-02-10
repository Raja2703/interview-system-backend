# apps/credits/tests/test_initial_credits.py
"""
Unit and integration tests for initial credit award functionality.

Tests cover:
1. CreditService.award_initial_credits() function
2. Role assignment triggering credit award
3. Edge cases and idempotency
4. Race condition prevention
"""

import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from concurrent.futures import ThreadPoolExecutor
import threading

from apps.credits.services import CreditService
from apps.credits.models import CreditBalance, CreditTransaction, TransactionType
from apps.profiles.models import UserProfile, Role


User = get_user_model()


class InitialCreditsTestCase(TestCase):
    """Tests for initial credit award functionality."""
    
    def setUp(self):
        """Create test user and profile."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
    
    def test_award_initial_credits_to_attender(self):
        """Test that attenders receive 1000 initial credits."""
        # Assign attender role
        self.profile.add_roles(['attender'])
        self.assertTrue(self.profile.is_attender())
        
        # Award credits
        success, message, txn = CreditService.award_initial_credits(self.user)
        
        # Verify success
        self.assertTrue(success)
        self.assertEqual(message, "Initial credits awarded")
        self.assertIsNotNone(txn)
        
        # Verify balance
        balance = CreditBalance.objects.get(user=self.user)
        self.assertEqual(balance.balance, 1000)
        self.assertEqual(balance.total_earned, 1000)
        self.assertTrue(balance.has_received_initial_credits)
        
        # Verify transaction record
        self.assertEqual(txn.amount, 1000)
        self.assertEqual(txn.transaction_type, TransactionType.INITIAL_CREDIT)
        self.assertEqual(txn.balance_after, 1000)
    
    def test_award_credits_non_attender_fails(self):
        """Test that non-attenders don't receive credits."""
        # User has no role
        self.assertFalse(self.profile.is_attender())
        
        success, message, txn = CreditService.award_initial_credits(self.user)
        
        self.assertFalse(success)
        self.assertEqual(message, "User is not an attender")
        self.assertIsNone(txn)
    
    def test_award_credits_taker_only_fails(self):
        """Test that takers-only don't receive initial credits."""
        self.profile.add_roles(['taker'])
        self.assertTrue(self.profile.is_taker())
        self.assertFalse(self.profile.is_attender())
        
        success, message, txn = CreditService.award_initial_credits(self.user)
        
        self.assertFalse(success)
        self.assertEqual(message, "User is not an attender")
        self.assertIsNone(txn)
    
    def test_award_credits_idempotent(self):
        """Test that credits are only awarded once (idempotency)."""
        self.profile.add_roles(['attender'])
        
        # First award
        success1, msg1, txn1 = CreditService.award_initial_credits(self.user)
        self.assertTrue(success1)
        
        # Second award attempt
        success2, msg2, txn2 = CreditService.award_initial_credits(self.user)
        
        self.assertFalse(success2)
        self.assertEqual(msg2, "Already credited")
        self.assertIsNone(txn2)
        
        # Balance should still be 1000
        balance = CreditBalance.objects.get(user=self.user)
        self.assertEqual(balance.balance, 1000)
        
        # Should only have one transaction
        txn_count = CreditTransaction.objects.filter(
            user=self.user,
            transaction_type=TransactionType.INITIAL_CREDIT
        ).count()
        self.assertEqual(txn_count, 1)
    
    def test_both_roles_gets_credits(self):
        """Test that users with both roles still get attender credits."""
        self.profile.add_roles(['attender', 'taker'])
        self.assertTrue(self.profile.is_attender())
        self.assertTrue(self.profile.is_taker())
        
        success, message, txn = CreditService.award_initial_credits(self.user)
        
        self.assertTrue(success)
        self.assertEqual(CreditBalance.objects.get(user=self.user).balance, 1000)


class CreditTransactionSaveTestCase(TestCase):
    """Test CreditTransaction.save() method handles UUID primary keys correctly."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='txnuser',
            email='txn@example.com',
            password='testpass123'
        )
    
    def test_create_transaction_succeeds(self):
        """Test that creating a new transaction works with UUID primary key."""
        txn = CreditTransaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.INITIAL_CREDIT,
            status='completed',
            amount=1000,
            balance_after=1000,
            description="Test initial credits"
        )
        
        self.assertIsNotNone(txn.id)
        self.assertEqual(txn.amount, 1000)
    
    def test_update_status_succeeds(self):
        """Test that updating transaction status works."""
        txn = CreditTransaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.INITIAL_CREDIT,
            status='pending',
            amount=1000,
            balance_after=1000,
            description="Test"
        )
        
        # Update status should work
        txn.status = 'completed'
        txn.save()
        
        txn.refresh_from_db()
        self.assertEqual(txn.status, 'completed')
    
    def test_update_amount_fails(self):
        """Test that modifying transaction amount raises error."""
        from django.core.exceptions import ValidationError
        
        txn = CreditTransaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.INITIAL_CREDIT,
            status='completed',
            amount=1000,
            balance_after=1000,
            description="Test"
        )
        
        # Try to modify amount
        txn.amount = 2000
        
        with self.assertRaises(ValidationError):
            txn.save()


class ConcurrentCreditsTestCase(TransactionTestCase):
    """Test race condition handling for concurrent credit awards."""
    
    def test_concurrent_credit_award_idempotent(self):
        """Test that concurrent award attempts only succeed once."""
        user = User.objects.create_user(
            username='concurrent_user',
            email='concurrent@example.com',
            password='testpass123'
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.add_roles(['attender'])
        
        # Create balance first to avoid race on balance creation
        CreditBalance.objects.get_or_create(user=user)
        
        results = []
        errors = []
        
        def award_credits():
            try:
                success, msg, txn = CreditService.award_initial_credits(user)
                results.append((success, msg))
            except Exception as e:
                errors.append(str(e))
        
        # Run 5 concurrent attempts
        threads = [threading.Thread(target=award_credits) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Check results - only one should succeed
        successes = [r for r in results if r[0] is True]
        self.assertEqual(len(successes), 1, f"Expected exactly 1 success, got {len(successes)}")
        
        # Balance should be exactly 1000
        balance = CreditBalance.objects.get(user=user)
        self.assertEqual(balance.balance, 1000)
        
        # Only one initial credit transaction should exist
        txn_count = CreditTransaction.objects.filter(
            user=user,
            transaction_type=TransactionType.INITIAL_CREDIT
        ).count()
        self.assertEqual(txn_count, 1)
