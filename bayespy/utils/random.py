######################################################################
# Copyright (C) 2013 Jaakko Luttinen
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
General functions random sampling and distributions.
"""

import numpy as np

from . import linalg
from . import utils

def intervals(N, length, amount=1, gap=0):
    """
    Return random non-overlapping parts of a sequence.

    For instance, N=16, length=2 and amount=4:
    [0, |1, 2|, 3, 4, 5, |6, 7|, 8, 9, |10, 11|, |12, 13|, 14, 15]
    that is,
    [1,2,6,7,10,11,12,13]

    However, the function returns only the indices of the beginning of the
    sequences, that is, in the example:
    [1,6,10,12]
    """

    if length * amount + gap * (amount-1) > N:
        raise ValueError("Too short sequence")

    # In practice, we draw the sizes of the gaps between the sequences
    total_gap = N - length*amount - gap*(amount-1)
    gaps = np.random.multinomial(total_gap, np.ones(amount+1)/(amount+1))

    # And then we get the beginning index of each sequence
    intervals = np.cumsum(gaps[:-1]) + np.arange(amount)*(length+gap)

    return intervals

def mask(*shape, p=0.5):
    """
    Return a boolean array of the given shape.

    Parameters:
    -----------
    d0, d1, ..., dn : int
        Shape of the output.
    p : value in range [0,1]
        A probability that the elements are `True`.
    """
    return np.random.rand(*shape) < p

def wishart_rand(nu, V):
    """
    Draw a random sample from the Wishart distribution.

    Parameters:
    -----------
    nu : int
    """
    # TODO/FIXME: Are these correct..
    D = np.shape(V)[0]
    if nu < D:
        raise ValueError("Degrees of freedom must be equal or greater than the "
                         "dimensionality of the matrix.")
    X = np.random.multivariate_normal(np.zeros(D), V, size=nu)
    return np.dot(X, X.T)

def invwishart_rand(nu, V):
    # TODO/FIXME: Are these correct..
    return np.linalg.inv(wishart_rand(nu, V))

def covariance(D, size=()):
    """
    Draw a random covariance matrix.

    Draws from inverse-Wishart distribution. The distribution of each element is
    independent of the dimensionality of the matrix.

    C ~ Inv-W(I, D)

    Parameters:
    -----------
    D : int
        Dimensionality of the covariance matrix.

    Returns:
    --------
    C : (D,D) ndarray
        Positive-definite symmetric :math:`D\times D` matrix.
    """

    if isinstance(size, int):
        size = (size,)
        
    shape = tuple(size) + (D,D)
    C = np.random.randn(*shape)
    C = linalg.dot(C, np.swapaxes(C, -1, -2))
    return linalg.inv(C)
#return np.linalg.inv(np.dot(C, C.T))

def correlation(D):
    """
    Draw a random correlation matrix.
    """
    X = np.random.randn(D,D);
    s = np.sqrt(np.sum(X**2, axis=-1, keepdims=True))
    X = X / s
    return np.dot(X, X.T)


def gaussian_logpdf(yVy, yVmu, muVmu, logdet_V, D):
    """
    Log-density of a Gaussian distribution.

    :math:`\mathcal{G}(\mathbf{y}|\boldsymbol{\mu},\mathbf{V}^{-1})`

    Parameters:
    -----------
    yVy : ndarray or double
        :math:`\mathbf{y}^T\mathbf{Vy}`
    yVmu : ndarray or double
        :math:`\mathbf{y}^T\mathbf{V}\boldsymbol{\mu}`
    muVmu : ndarray or double
        :math:`\boldsymbol{\mu}^T\mathbf{V}\boldsymbol{\mu}`
    logdet_V : ndarray or double
        Log-determinant of the precision matrix, :math:`\log|\mathbf{V}|`.
    D : int
        Dimensionality of the distribution.
    """
    return -0.5*yVy + yVmu - 0.5*muVmu + 0.5*logdet_V - 0.5*D*np.log(2*np.pi)

def gaussian_entropy(logdet_V, D):
    """
    Compute the entropy of a Gaussian distribution.

    If you want to get the gradient, just let each parameter be a gradient of
    that term.

    Parameters:
    -----------
    logdet_V : ndarray or double
        The log-determinant of the precision matrix.
    D : int
        The dimensionality of the distribution.
    """
    return -0.5*logdet_V + 0.5*D + 0.5*D*np.log(2*np.pi)

def gamma_logpdf(bx, logx, a_logx, a_logb, gammaln_a):
    """
    Log-density of :math:`\mathcal{G}(x|a,b)`.
    
    If you want to get the gradient, just let each parameter be a gradient of
    that term.

    Parameters:
    -----------
    bx : ndarray
        :math:`bx`
    logx : ndarray
        :math:`\log(x)`
    a_logx : ndarray
        :math:`a \log(x)`
    a_logb : ndarray
        :math:`a \log(b)`
    gammaln_a : ndarray
        :math:`\log\Gamma(a)`
    """
    return a_logb - gammaln_a + a_logx - logx - bx
#def gamma_logpdf(a, log_b, gammaln_a, 

def gamma_entropy(a, log_b, gammaln_a, psi_a, a_psi_a):
    """
    Entropy of :math:`\mathcal{G}(a,b)`.

    If you want to get the gradient, just let each parameter be a gradient of
    that term.

    Parameters:
    -----------
    a : ndarray
        :math:`a`
    log_b : ndarray
        :math:`\log(b)`
    gammaln_a : ndarray
        :math:`\log\Gamma(a)`
    psi_a : ndarray
        :math:`\psi(a)`
    a_psi_a : ndarray
        :math:`a\psi(a)`
    """
    return a - log_b + gammaln_a + psi_a - a_psi_a

def orth(D):
    """
    Draw random orthogonal matrix.
    """
    Q = np.random.randn(D,D)
    (Q, _) = np.linalg.qr(Q)
    return Q

def svd(s):
    """
    Draw a random matrix given its singular values.
    """
    D = len(s)
    U = orth(D) * s
    V = orth(D)
    return np.dot(U, V.T)
    
def sphere(N=1):
    """
    Draw random points uniformly on a unit sphere.

    Returns (latitude,longitude) in degrees.
    """
    lon = np.random.uniform(-180, 180, N)
    lat = (np.arccos(np.random.uniform(-1, 1, N)) * 180 / np.pi) - 90
    return (lat, lon)

def categorical(p, size=None):
    """
    Draw random samples from a categorical distribution.
    """
    if size is None:
        size = np.shape(p)[:-1]

    if np.any(np.asanyarray(p)<0):
        raise ValueError("Array contains negative probabilities")

    if not utils.is_shape_subset(np.shape(p)[:-1], size):
        raise ValueError("Probability array shape and requested size are "
                         "inconsistent")

    size = tuple(size)

    # Normalize probabilities
    p = p / np.sum(p, axis=-1, keepdims=True)

    # Compute cumulative probabilities (p_1, p_1+p_2, ..., p_1+...+p_N):
    P = np.cumsum(p, axis=-1)

    # Draw samples from interval [0,1]
    x = np.random.rand(*size)

    # For simplicity, repeat p to the size of the output (plus probability axis)
    K = np.shape(p)[-1]
    P = P * np.ones(tuple(size)+(K,))

    if size == ():
        z = np.searchsorted(P, x)
    else:
        # Seach the indices
        z = np.zeros(size)
        inds = utils.nested_iterator(size)
        for ind in inds:
            z[ind] = np.searchsorted(P[ind], x[ind])

    return z

def alpha_beta_recursion(logp0, logP):
    """
    Compute alpha-beta recursion for Markov chain

    Initial state log-probabilities are in `p0` and state transition
    log-probabilities are in P. The probabilities do not need to be scaled to
    sum to one, but they are interpreted as below:

    logp0 = log P(z_0) + log P(y_0|z_0)
    logP[...,n,:,:] = log P(z_{n+1}|z_n) + log P(y_{n+1}|z_{n+1})
    """

    logp0 = utils.atleast_nd(logp0, 1)
    logP = utils.atleast_nd(logP, 3)
    
    D = np.shape(logp0)[-1]
    N = np.shape(logP)[-3]
    plates = utils.broadcasted_shape(np.shape(logp0)[:-1], np.shape(logP)[:-3])

    if np.shape(logP)[-2:] != (D,D):
        raise ValueError("Dimension mismatch %s != %s"
                         % (np.shape(logP)[-2:],
                            (D,D)))

    #
    # Run the recursion algorithm
    #

    # Allocate memory
    logalpha = np.zeros(plates+(N,D))
    logbeta = np.zeros(plates+(N,D))
    g = np.zeros(plates)

    # Forward recursion
    logalpha[...,0,:] = logp0
    for n in range(1,N):
        # Compute: P(z_{n-1},z_n|x_1,...,x_n)
        v = logalpha[...,n-1,:,None] + logP[...,n-1,:,:]
        c = utils.logsumexp(v, axis=(-1,-2))
        # Sum over z_{n-1} to get: log P(z_n|x_1,...,x_n)
        logalpha[...,n,:] = utils.logsumexp(v - c[...,None,None], axis=-2)
        g -= c

    # Compute the normalization of the last term
    v = logalpha[...,N-1,:,None] + logP[...,N-1,:,:]
    g -= utils.logsumexp(v, axis=(-1,-2))

    # Backward recursion 
    logbeta[...,N-1,:] = 0
    for n in reversed(range(N-1)):
        v = logbeta[...,n+1,None,:] + logP[...,n+1,:,:]
        c = utils.logsumexp(v, axis=(-1,-2))
        logbeta[...,n,:] = utils.logsumexp(v - c[...,None,None], axis=-1)

    v = logalpha[...,:,:,None] + logbeta[...,:,None,:] + logP[...,:,:,:]
    c = utils.logsumexp(v, axis=(-1,-2))
    zz = np.exp(v - c[...,None,None])

    # The logsumexp normalization is not numerically accurate, so do
    # normalization again:
    zz /= np.sum(zz, axis=(-1,-2), keepdims=True)

    z0 = np.sum(zz[...,0,:,:], axis=-1)

    return (z0, zz, g)
