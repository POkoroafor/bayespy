######################################################################
# Copyright (C) 2013,2014 Jaakko Luttinen
#
# This file is licensed under Version 3.0 of the GNU General Public
# License. See LICENSE for a text of the license.
######################################################################

######################################################################
# This file is part of BayesPy.
#
# BayesPy is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# BayesPy is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BayesPy.  If not, see <http://www.gnu.org/licenses/>.
######################################################################

"""
Unit tests for `dot` module.
"""

import unittest


import numpy as np
import scipy

from numpy import testing

from ..dot import Dot, SumMultiply
from ..gaussian import Gaussian, GaussianARD

from ...vmp import VB

from bayespy.utils import utils
from bayespy.utils import linalg
from bayespy.utils import random

from bayespy.utils.utils import TestCase

class TestSumMultiply(TestCase):

    def test_parent_validity(self):
        """
        Test that the parent nodes are validated properly in SumMultiply
        """
        V = GaussianARD(1, 1)
        X = Gaussian(np.ones(1), np.identity(1))
        Y = Gaussian(np.ones(3), np.identity(3))
        Z = Gaussian(np.ones(5), np.identity(5))

        A = SumMultiply(X, ['i'])
        self.assertEqual(A.dims, ((), ()))
        A = SumMultiply('i', X)
        self.assertEqual(A.dims, ((), ()))
        
        A = SumMultiply(X, ['i'], ['i'])
        self.assertEqual(A.dims, ((1,), (1,1)))
        A = SumMultiply('i->i', X)
        self.assertEqual(A.dims, ((1,), (1,1)))
        
        A = SumMultiply(X, ['i'], Y, ['j'], ['i','j'])
        self.assertEqual(A.dims, ((1,3), (1,3,1,3)))
        A = SumMultiply('i,j->ij', X, Y)
        self.assertEqual(A.dims, ((1,3), (1,3,1,3)))
        
        A = SumMultiply(V, [], X, ['i'], Y, ['i'], [])
        self.assertEqual(A.dims, ((), ()))
        A = SumMultiply(',i,i->', V, X, Y)
        self.assertEqual(A.dims, ((), ()))

        # Error: not enough inputs
        self.assertRaises(ValueError,
                          SumMultiply)
        self.assertRaises(ValueError,
                          SumMultiply,
                          X)
        # Error: too many keys
        self.assertRaises(ValueError,
                          SumMultiply,
                          Y, 
                          ['i', 'j'])
        self.assertRaises(ValueError,
                          SumMultiply,
                          'ij',
                          Y)
        # Error: not broadcastable
        self.assertRaises(ValueError,
                          SumMultiply,
                          Y,
                          ['i'],
                          Z,
                          ['i'])
        self.assertRaises(ValueError,
                          SumMultiply,
                          'i,i',
                          Y,
                          Z)
        # Error: output key not in inputs
        self.assertRaises(ValueError,
                          SumMultiply,
                          X,
                          ['i'],
                          ['j'])
        self.assertRaises(ValueError,
                          SumMultiply,
                          'i->j',
                          X)
        # Error: non-unique input keys
        self.assertRaises(ValueError,
                          SumMultiply,
                          X,
                          ['i','i'])
        self.assertRaises(ValueError,
                          SumMultiply,
                          'ii',
                          X)
        # Error: non-unique output keys
        self.assertRaises(ValueError,
                          SumMultiply,
                          X,
                          ['i'],
                          ['i','i'])
        self.assertRaises(ValueError,
                          SumMultiply,
                          'i->ii',
                          X)                          
        # String has too many '->'
        self.assertRaises(ValueError,
                          SumMultiply,
                          'i->i->i',
                          X)
        # String has too many input nodes
        self.assertRaises(ValueError,
                          SumMultiply,
                          'i,i->i',
                          X)

    def test_message_to_child(self):
        """
        Test the message from SumMultiply to its children.
        """

        def compare_moments(u0, u1, *args):
            Y = SumMultiply(*args)
            u_Y = Y.get_moments()
            self.assertAllClose(u_Y[0], u0)
            self.assertAllClose(u_Y[1], u1)

        # Test constant parent
        y = np.random.randn(2,3,4)
        compare_moments(y,
                        linalg.outer(y, y, ndim=2),
                        'ij->ij',
                        y)

        # Do nothing for 2-D array
        Y = GaussianARD(np.random.randn(5,2,3),
                        np.random.rand(5,2,3),
                        plates=(5,),
                        shape=(2,3))
        y = Y.get_moments()
        compare_moments(y[0],
                        y[1],
                        'ij->ij',
                        Y)
        compare_moments(y[0],
                        y[1],
                        Y,
                        [0,1],
                        [0,1])

        # Sum over the rows of a matrix
        Y = GaussianARD(np.random.randn(5,2,3),
                        np.random.rand(5,2,3),
                        plates=(5,),
                        shape=(2,3))
        y = Y.get_moments()
        mu = np.einsum('...ij->...j', y[0])
        cov = np.einsum('...ijkl->...jl', y[1])
        compare_moments(mu,
                        cov,
                        'ij->j',
                        Y)
        compare_moments(mu,
                        cov,
                        Y,
                        [0,1],
                        [1])

        # Inner product of three vectors
        X1 = GaussianARD(np.random.randn(2),
                         np.random.rand(2),
                         plates=(),
                         shape=(2,))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(6,1,2),
                         np.random.rand(6,1,2),
                         plates=(6,1),
                         shape=(2,))
        x2 = X2.get_moments()
        X3 = GaussianARD(np.random.randn(7,6,5,2),
                         np.random.rand(7,6,5,2),
                         plates=(7,6,5),
                         shape=(2,))
        x3 = X3.get_moments()
        mu = np.einsum('...i,...i,...i->...', x1[0], x2[0], x3[0])
        cov = np.einsum('...ij,...ij,...ij->...', x1[1], x2[1], x3[1])
        compare_moments(mu,
                        cov,
                        'i,i,i',
                        X1,
                        X2,
                        X3)
        compare_moments(mu,
                        cov,
                        'i,i,i->',
                        X1,
                        X2,
                        X3)
        compare_moments(mu,
                        cov,
                        X1,
                        [9],
                        X2,
                        [9],
                        X3,
                        [9])
        compare_moments(mu,
                        cov,
                        X1,
                        [9],
                        X2,
                        [9],
                        X3,
                        [9],
                        [])
                            

        # Outer product of two vectors
        X1 = GaussianARD(np.random.randn(2),
                         np.random.rand(2),
                         plates=(5,),
                         shape=(2,))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(6,1,2),
                         np.random.rand(6,1,2),
                         plates=(6,1),
                         shape=(2,))
        x2 = X2.get_moments()
        mu = np.einsum('...i,...j->...ij', x1[0], x2[0])
        cov = np.einsum('...ik,...jl->...ijkl', x1[1], x2[1])
        compare_moments(mu,
                        cov,
                        'i,j->ij',
                        X1,
                        X2)
        compare_moments(mu,
                        cov,
                        X1,
                        [9],
                        X2,
                        [7],
                        [9,7])

        # Matrix product
        Y1 = GaussianARD(np.random.randn(3,2),
                         np.random.rand(3,2),
                         plates=(),
                         shape=(3,2))
        y1 = Y1.get_moments()
        Y2 = GaussianARD(np.random.randn(5,2,3),
                         np.random.rand(5,2,3),
                         plates=(5,),
                         shape=(2,3))
        y2 = Y2.get_moments()
        mu = np.einsum('...ik,...kj->...ij', y1[0], y2[0])
        cov = np.einsum('...ikjl,...kmln->...imjn', y1[1], y2[1])
        compare_moments(mu,
                        cov,
                        'ik,kj->ij',
                        Y1,
                        Y2)
        compare_moments(mu,
                        cov,
                        Y1,
                        ['i','k'],
                        Y2,
                        ['k','j'],
                        ['i','j'])

        # Trace of a matrix product
        Y1 = GaussianARD(np.random.randn(3,2),
                         np.random.rand(3,2),
                         plates=(),
                         shape=(3,2))
        y1 = Y1.get_moments()
        Y2 = GaussianARD(np.random.randn(5,2,3),
                         np.random.rand(5,2,3),
                         plates=(5,),
                         shape=(2,3))
        y2 = Y2.get_moments()
        mu = np.einsum('...ij,...ji->...', y1[0], y2[0])
        cov = np.einsum('...ikjl,...kilj->...', y1[1], y2[1])
        compare_moments(mu,
                        cov,
                        'ij,ji',
                        Y1,
                        Y2)
        compare_moments(mu,
                        cov,
                        'ij,ji->',
                        Y1,
                        Y2)
        compare_moments(mu,
                        cov,
                        Y1,
                        ['i','j'],
                        Y2,
                        ['j','i'])
        compare_moments(mu,
                        cov,
                        Y1,
                        ['i','j'],
                        Y2,
                        ['j','i'],
                        [])

        # Vector-matrix-vector product
        X1 = GaussianARD(np.random.randn(3),
                         np.random.rand(3),
                         plates=(),
                         shape=(3,))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(6,1,2),
                         np.random.rand(6,1,2),
                         plates=(6,1),
                         shape=(2,))
        x2 = X2.get_moments()
        Y = GaussianARD(np.random.randn(3,2),
                        np.random.rand(3,2),
                        plates=(),
                        shape=(3,2))
        y = Y.get_moments()
        mu = np.einsum('...i,...ij,...j->...', x1[0], y[0], x2[0])
        cov = np.einsum('...ia,...ijab,...jb->...', x1[1], y[1], x2[1])
        compare_moments(mu,
                        cov,
                        'i,ij,j',
                        X1,
                        Y,
                        X2)
        compare_moments(mu,
                        cov,
                        X1,
                        [1],
                        Y,
                        [1,2],
                        X2,
                        [2])
        
        # Complex sum-product of 0-D, 1-D, 2-D and 3-D arrays
        V = GaussianARD(np.random.randn(7,6,5),
                        np.random.rand(7,6,5),
                        plates=(7,6,5),
                        shape=())
        v = V.get_moments()
        X = GaussianARD(np.random.randn(6,1,2),
                        np.random.rand(6,1,2),
                        plates=(6,1),
                        shape=(2,))
        x = X.get_moments()
        Y = GaussianARD(np.random.randn(3,4),
                        np.random.rand(3,4),
                        plates=(5,),
                        shape=(3,4))
        y = Y.get_moments()
        Z = GaussianARD(np.random.randn(4,2,3),
                        np.random.rand(4,2,3),
                        plates=(6,5),
                        shape=(4,2,3))
        z = Z.get_moments()
        mu = np.einsum('...,...i,...kj,...jik->...k', v[0], x[0], y[0], z[0])
        cov = np.einsum('...,...ia,...kjcb,...jikbac->...kc', v[1], x[1], y[1], z[1])
        compare_moments(mu,
                        cov,
                        ',i,kj,jik->k',
                        V,
                        X,
                        Y,
                        Z)
        compare_moments(mu,
                        cov,
                        V,
                        [],
                        X,
                        ['i'],
                        Y,
                        ['k','j'],
                        Z,
                        ['j','i','k'],
                        ['k'])

        pass

    def test_message_to_parent(self):
        """
        Test the message from SumMultiply node to its parents.
        """

        data = 2
        tau = 3
        
        def check_message(true_m0, true_m1, parent, *args, F=None):
            if F is None:
                A = SumMultiply(*args)
                B = GaussianARD(A, tau)
                B.observe(data*np.ones(A.plates + A.dims[0]))
            else:
                A = F
            (A_m0, A_m1) = A._message_to_parent(parent)
            self.assertAllClose(true_m0, A_m0)
            self.assertAllClose(true_m1, A_m1)
            pass

        # Check: different message to each of multiple parents
        X1 = GaussianARD(np.random.randn(2),
                         np.random.rand(2))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(2),
                         np.random.rand(2))
        x2 = X2.get_moments()
        m0 = tau * data * x2[0]
        m1 = -0.5 * tau * x2[1] * np.identity(2)
        check_message(m0, m1, 0,
                      'i,i->i',
                      X1,
                      X2)
        check_message(m0, m1, 0,
                      X1,
                      [9],
                      X2,
                      [9],
                      [9])
        m0 = tau * data * x1[0]
        m1 = -0.5 * tau * x1[1] * np.identity(2)
        check_message(m0, m1, 1,
                      'i,i->i',
                      X1,
                      X2)
        check_message(m0, m1, 1,
                      X1,
                      [9],
                      X2,
                      [9],
                      [9])
        
        # Check: key not in output
        X1 = GaussianARD(np.random.randn(2),
                         np.random.rand(2))
        x1 = X1.get_moments()
        m0 = tau * data * np.ones(2)
        m1 = -0.5 * tau * np.ones((2,2))
        check_message(m0, m1, 0,
                      'i',
                      X1)
        check_message(m0, m1, 0,
                      'i->',
                      X1)
        check_message(m0, m1, 0,
                      X1,
                      [9])
        check_message(m0, m1, 0,
                      X1,
                      [9],
                      [])

        # Check: key not in some input
        X1 = GaussianARD(np.random.randn(),
                         np.random.rand())
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(2),
                         np.random.rand(2))
        x2 = X2.get_moments()
        m0 = tau * data * np.sum(x2[0], axis=-1)
        m1 = -0.5 * tau * np.sum(x2[1] * np.identity(2),
                                 axis=(-1,-2))
        check_message(m0, m1, 0,
                      ',i->i',
                      X1,
                      X2)
        check_message(m0, m1, 0,
                      X1,
                      [],
                      X2,
                      [9],
                      [9])
        m0 = tau * data * x1[0] * np.ones(2)
        m1 = -0.5 * tau * x1[1] * np.identity(2)
        check_message(m0, m1, 1,
                      ',i->i',
                      X1,
                      X2)
        check_message(m0, m1, 1,
                      X1,
                      [],
                      X2,
                      [9],
                      [9])

        # Check: keys in different order
        Y1 = GaussianARD(np.random.randn(3,2),
                         np.random.rand(3,2))
        y1 = Y1.get_moments()
        Y2 = GaussianARD(np.random.randn(2,3),
                         np.random.rand(2,3))
        y2 = Y2.get_moments()
        m0 = tau * data * y2[0].T
        m1 = -0.5 * tau * np.einsum('ijlk->jikl', y2[1] * utils.identity(2,3))
        check_message(m0, m1, 0,
                      'ij,ji->ij',
                      Y1,
                      Y2)
        check_message(m0, m1, 0,
                      Y1,
                      ['i','j'],
                      Y2,
                      ['j','i'],
                      ['i','j'])
        m0 = tau * data * y1[0].T
        m1 = -0.5 * tau * np.einsum('ijlk->jikl', y1[1] * utils.identity(3,2))
        check_message(m0, m1, 1,
                      'ij,ji->ij',
                      Y1,
                      Y2)
        check_message(m0, m1, 1,
                      Y1,
                      ['i','j'],
                      Y2,
                      ['j','i'],
                      ['i','j'])

        # Check: plates when different dimensionality
        X1 = GaussianARD(np.random.randn(5),
                         np.random.rand(5),
                         shape=(),
                         plates=(5,))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(5,3),
                         np.random.rand(5,3),
                         shape=(3,),
                         plates=(5,))
        x2 = X2.get_moments()
        m0 = tau * data * np.sum(np.ones((5,3)) * x2[0], axis=-1)
        m1 = -0.5 * tau * np.sum(x2[1] * utils.identity(3), axis=(-1,-2))
        check_message(m0, m1, 0,
                      ',i->i',
                      X1,
                      X2)
        check_message(m0, m1, 0,
                      X1,
                      [],
                      X2,
                      ['i'],
                      ['i'])
        m0 = tau * data * x1[0][:,np.newaxis] * np.ones((5,3))
        m1 = -0.5 * tau * x1[1][:,np.newaxis,np.newaxis] * utils.identity(3)
        check_message(m0, m1, 1,
                      ',i->i',
                      X1,
                      X2)
        check_message(m0, m1, 1,
                      X1,
                      [],
                      X2,
                      ['i'],
                      ['i'])
        
        # Check: other parent's moments broadcasts over plates when node has the
        # same plates
        X1 = GaussianARD(np.random.randn(5,4,3),
                         np.random.rand(5,4,3),
                         shape=(3,),
                         plates=(5,4))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(3),
                         np.random.rand(3),
                         shape=(3,),
                         plates=(5,4))
        x2 = X2.get_moments()
        m0 = tau * data * np.ones((5,4,3)) * x2[0]
        m1 = -0.5 * tau * x2[1] * utils.identity(3)
        check_message(m0, m1, 0,
                      'i,i->i',
                      X1,
                      X2)
        check_message(m0, m1, 0,
                      X1,
                      ['i'],
                      X2,
                      ['i'],
                      ['i'])
        
        # Check: other parent's moments broadcasts over plates when node does
        # not have that plate
        X1 = GaussianARD(np.random.randn(3),
                         np.random.rand(3),
                         shape=(3,),
                         plates=())
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(3),
                         np.random.rand(3),
                         shape=(3,),
                         plates=(5,4))
        x2 = X2.get_moments()
        m0 = tau * data * np.sum(np.ones((5,4,3)) * x2[0], axis=(0,1))
        m1 = -0.5 * tau * np.sum(np.ones((5,4,1,1))
                                 * utils.identity(3)
                                 * x2[1], 
                                 axis=(0,1))
        check_message(m0, m1, 0,
                      'i,i->i',
                      X1,
                      X2)
        check_message(m0, m1, 0,
                      X1,
                      ['i'],
                      X2,
                      ['i'],
                      ['i'])
        
        # Check: other parent's moments broadcasts over plates when the node
        # only broadcasts that plate
        X1 = GaussianARD(np.random.randn(3),
                         np.random.rand(3),
                         shape=(3,),
                         plates=(1,1))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(3),
                         np.random.rand(3),
                         shape=(3,),
                         plates=(5,4))
        x2 = X2.get_moments()
        m0 = tau * data * np.sum(np.ones((5,4,3)) * x2[0], axis=(0,1), keepdims=True)
        m1 = -0.5 * tau * np.sum(np.ones((5,4,1,1))
                                 * utils.identity(3)
                                 * x2[1], 
                                 axis=(0,1),
                                 keepdims=True)
        check_message(m0, m1, 0,
                      'i,i->i',
                      X1,
                      X2)
        check_message(m0, m1, 0,
                      X1,
                      ['i'],
                      X2,
                      ['i'],
                      ['i'])
        
        # Check: broadcasted dimensions
        X1 = GaussianARD(np.random.randn(1,1),
                         np.random.rand(1,1))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(3,2),
                         np.random.rand(3,2))
        x2 = X2.get_moments()
        m0 = tau * data * np.sum(np.ones((3,2)) * x2[0], 
                                 keepdims=True)
        m1 = -0.5 * tau * np.sum(utils.identity(3,2) * x2[1], 
                                 keepdims=True)
        check_message(m0, m1, 0,
                      'ij,ij->ij',
                      X1,
                      X2)
        check_message(m0, m1, 0,
                      X1,
                      [0,1],
                      X2,
                      [0,1],
                      [0,1])
        m0 = tau * data * np.ones((3,2)) * x1[0]
        m1 = -0.5 * tau * utils.identity(3,2) * x1[1]
        check_message(m0, m1, 1,
                      'ij,ij->ij',
                      X1,
                      X2)
        check_message(m0, m1, 1,
                      X1,
                      [0,1],
                      X2,
                      [0,1],
                      [0,1])

        # Check: non-ARD observations
        X1 = GaussianARD(np.random.randn(2),
                         np.random.rand(2))
        x1 = X1.get_moments()
        Lambda = np.array([[2, 1.5], [1.5, 2]])
        F = SumMultiply('i->i', X1)
        Y = Gaussian(F, Lambda)
        y = np.random.randn(2)
        Y.observe(y)
        m0 = np.dot(Lambda, y)
        m1 = -0.5 * Lambda
        check_message(m0, m1, 0,
                      'i->i',
                      X1,
                      F=F)
        check_message(m0, m1, 0,
                      X1,
                      ['i'],
                      ['i'],
                      F=F)

        # Check: mask with same shape
        X1 = GaussianARD(np.random.randn(3,2),
                         np.random.rand(3,2),
                         shape=(2,),
                         plates=(3,))
        x1 = X1.get_moments()
        mask = np.array([True, False, True])
        F = SumMultiply('i->i', X1)
        Y = GaussianARD(F, tau)                     
        Y.observe(data*np.ones((3,2)), mask=mask)
        m0 = tau * data * mask[:,np.newaxis] * np.ones(2)
        m1 = -0.5 * tau * mask[:,np.newaxis,np.newaxis] * np.identity(2)
        check_message(m0, m1, 0,
                      'i->i',
                      X1,
                      F=F)
        check_message(m0, m1, 0,
                      X1,
                      ['i'],
                      ['i'],
                      F=F)

        # Check: mask larger
        X1 = GaussianARD(np.random.randn(2),
                         np.random.rand(2),
                         shape=(2,),
                         plates=())
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(3,2),
                         np.random.rand(3,2),
                         shape=(2,),
                         plates=(3,))
        x2 = X2.get_moments()
        mask = np.array([True, False, True])
        F = SumMultiply('i,i->i', X1, X2)
        Y = GaussianARD(F, tau,
                        plates=(3,))                     
        Y.observe(data*np.ones((3,2)), mask=mask)
        m0 = tau * data * np.sum(mask[:,np.newaxis] * x2[0], axis=0)
        m1 = -0.5 * tau * np.sum(mask[:,np.newaxis,np.newaxis]
                                 * x2[1]
                                 * np.identity(2),
                                 axis=0)
        check_message(m0, m1, 0,
                      'i,i->i',
                      X1,
                      X2,
                      F=F)
        check_message(m0, m1, 0,
                      X1,
                      ['i'],
                      X2,
                      ['i'],
                      ['i'],
                      F=F)

        # Check: mask for broadcasted plate
        X1 = GaussianARD(np.random.randn(2),
                         np.random.rand(2),
                         plates=(1,))
        x1 = X1.get_moments()
        X2 = GaussianARD(np.random.randn(2),
                         np.random.rand(2),
                         plates=(3,))
        x2 = X2.get_moments()
        mask = np.array([True, False, True])
        F = SumMultiply('i,i->i', X1, X2)
        Y = GaussianARD(F, tau,
                        plates=(3,))
        Y.observe(data*np.ones((3,2)), mask=mask)
        m0 = tau * data * np.sum(mask[:,np.newaxis] * x2[0], 
                                 axis=0,
                                 keepdims=True)
        m1 = -0.5 * tau * np.sum(mask[:,np.newaxis,np.newaxis]
                                 * x2[1]
                                 * np.identity(2),
                                 axis=0,
                                 keepdims=True)
        check_message(m0, m1, 0,
                      'i->i',
                      X1,
                      F=F)
        check_message(m0, m1, 0,
                      X1,
                      ['i'],
                      ['i'],
                      F=F)

        pass

def check_performance(scale=1e2):
    """
    Tests that the implementation of SumMultiply is efficient.

    This is not a unit test (not run automatically), but rather a
    performance test, which you may run to test the performance of the
    node. A naive implementation of SumMultiply will run out of memory in
    some cases and this method checks that the implementation is not naive
    but good.
    """

    # Check: Broadcasted plates are computed efficiently
    # (bad implementation will take a long time to run)
    s = scale
    X1 = GaussianARD(np.random.randn(s,s),
                     np.random.rand(s,s),
                     shape=(s,),
                     plates=(s,))
    X2 = GaussianARD(np.random.randn(s,1,s),
                     np.random.rand(s,1,s),
                     shape=(s,),
                     plates=(s,1))
    F = SumMultiply('i,i', X1, X2)
    Y = GaussianARD(F, 1)
    Y.observe(np.ones((s,s)))
    try:
        F._message_to_parent(1)
    except e:
        print(e)
        print('SOMETHING BAD HAPPENED')


    # Check: Broadcasted dimensions are computed efficiently
    # (bad implementation will run out of memory)

    pass
