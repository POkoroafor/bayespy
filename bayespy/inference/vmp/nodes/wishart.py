######################################################################
# Copyright (C) 2011,2012,2014 Jaakko Luttinen
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

import numpy as np
import scipy.special as special

from bayespy.utils import utils

from .expfamily import ExponentialFamily
from .expfamily import ExponentialFamilyDistribution
from .expfamily import useconstructor
from .constant import Constant

from .node import Moments, Node
class WishartPriorMoments(Moments):
    ndim_observations = 0
    def __init__(self, k):
        self.k = k
        return
    
    def compute_fixed_moments(self, n):
        """ Compute moments for fixed x. """
        u0 = np.asanyarray(n)
        u1 = special.multigammaln(0.5*u0, self.k)
        return [u0, u1]

    def compute_dims_from_values(self, n):
        """ Compute the dimensions of phi or u. """
        return ( (), () )

class WishartMoments(Moments):
    ndim_observations = 2
    def compute_fixed_moments(self, Lambda):
        """ Compute moments for fixed x. """
        ldet = utils.m_chol_logdet(utils.m_chol(Lambda))
        u = [Lambda,
             ldet]
        return u

    def compute_dims_from_values(self, x):
        """ Compute the dimensions of phi and u. """
        if np.ndim(x) < 2:
            raise ValueError("Values for Wishart distribution must be at least "
                             "2-D arrays.")
        if np.shape(x)[-1] != np.shape(x)[-2]:
            raise ValueError("Values for Wishart distribution must be square "
                             "matrices, thus the two last axes must have equal "
                             "length.")
        d = np.shape(x)[-1]
        return ( (d,d), () )

class WishartDistribution(ExponentialFamilyDistribution):
    """
    Sub-classes implement distribution specific computations.
    """

    ndims = (2, 0)
    ndims_parents = [None, (2, 0)]

    def compute_message_to_parent(self, parent, index, u_self, *u_parents):
        raise NotImplementedError()

    def compute_phi_from_parents(self, *u_parents, mask=True):
        return [-0.5 * u_parents[1][0],
                0.5 * u_parents[0][0]]

    def compute_moments_and_cgf(self, phi, mask=True):
        U = utils.m_chol(-phi[0])
        k = np.shape(phi[0])[-1]
        #k = self.dims[0][0]
        logdet_phi0 = utils.m_chol_logdet(U)
        u0 = phi[1][...,np.newaxis,np.newaxis] * utils.m_chol_inv(U)
        u1 = -logdet_phi0 + utils.m_digamma(phi[1], k)
        u = [u0, u1]
        g = phi[1] * logdet_phi0 - special.multigammaln(phi[1], k)
        return (u, g)

    def compute_cgf_from_parents(self, *u_parents):
        n = u_parents[0][0]
        gammaln_n = u_parents[0][1]
        V = u_parents[1][0]
        logdet_V = u_parents[1][1]
        k = np.shape(V)[-1]
        #k = self.dims[0][0]
        # TODO: Check whether this is correct:
        #g = 0.5*n*logdet_V - special.multigammaln(n/2, k)
        g = 0.5*n*logdet_V - 0.5*k*n*np.log(2) - gammaln_n #special.multigammaln(n/2, k)
        return g

    def compute_fixed_moments_and_f(self, Lambda, mask=True):
        """ Compute u(x) and f(x) for given x. """
        k = np.shape(Lambda)[-1]
        ldet = utils.m_chol_logdet(utils.m_chol(Lambda))
        u = [Lambda,
             ldet]
        f = -(k+1)/2 * ldet
        return (u, f)

    def shape_of_value(self, dims):
        return dims[0]

class Wishart(ExponentialFamily):

    _distribution = WishartDistribution()
    _moments = WishartMoments()

    @useconstructor
    def __init__(self, n, V, **kwargs):
        super().__init__(n, V, **kwargs)
        
    @classmethod
    def _constructor(cls, n, V, plates=None, **kwargs):
        """
        Constructs distribution and moments objects.
        """

        # Make V a proper parent node and get the dimensionality of the matrix
        V = cls._ensure_moments(V, WishartMoments())
        k = V.dims[0][-1]

        # Parent node message types
        parent_moments = (WishartPriorMoments(k), 
                          WishartMoments())

        # Dimensionality of the natural parameters
        dims = ( (k,k), () )

        n = cls._ensure_moments(n, parent_moments[0])
        
        return (dims, 
                cls._total_plates(plates,
                                  cls._distribution.plates_from_parent(0, n.plates),
                                  cls._distribution.plates_from_parent(1, V.plates)),
                cls._distribution, 
                cls._moments, 
                parent_moments)

    def show(self):
        print("%s ~ Wishart(n, A)" % self.name)
        print("  n =")
        print(2*self.phi[1])
        print("  A =")
        print(0.5 * self.u[0] / self.phi[1][...,np.newaxis,np.newaxis])

