######################################################################
# Copyright (C) 2013-2014 Jaakko Luttinen
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
import warnings
import scipy

from bayespy import utils
from bayespy.utils.linalg import dot, tracedot

from .nodes import gaussian

from .nodes.categorical import CategoricalMoments

class RotationOptimizer():

    def __init__(self, block1, block2, D):
        self.block1 = block1
        self.block2 = block2
        self.D = D

    def rotate(self, 
               maxiter=10, 
               check_gradient=False,
               verbose=False,
               check_bound=False):
        """
        Optimize the rotation of two separate model blocks jointly.

        If some variable is the dot product of two Gaussians, rotating the two
        Gaussians optimally can make the inference algorithm orders of magnitude
        faster.

        First block is rotated with :math:`\mathbf{R}` and the second with
        :math:`\mathbf{R}^{-T}`.

        Blocks must have methods: `bound(U,s,V)` and `rotate(R)`.
        """

        I = np.identity(self.D)
        piv = np.arange(self.D)
        
        def cost(r):

            # Make vector-r into matrix-R
            R = np.reshape(r, (self.D,self.D))

            # Compute SVD
            invR = np.linalg.inv(R)
            logdetR = np.linalg.slogdet(R)[1]

            # Compute lower bound terms
            (b1,db1) = self.block1.bound(R, logdet=logdetR, inv=invR)
            (b2,db2) = self.block2.bound(invR.T, logdet=-logdetR, inv=R.T)

            # Apply chain rule for the second gradient:
            # d b(invR.T) 
            # = tr(db.T * d(invR.T)) 
            # = tr(db * d(invR))
            # = -tr(db * invR * (dR) * invR) 
            # = -tr(invR * db * invR * dR)
            db2 = -dot(invR.T, db2.T, invR.T)

            # Compute the cost function
            c = -(b1+b2)
            dc = -(db1+db2)

            return (c, np.ravel(dc))

        def get_bound_terms(r, gradient=False):
            """
            Returns a dictionary of bound terms for the nodes.
            """
            # Gradient not yet implemented..
            if gradient:
                raise NotImplementedError()
            
            # Make vector-r into matrix-R
            R = np.reshape(r, (self.D,self.D))

            # Compute SVD
            invR = np.linalg.inv(R)
            logdetR = np.linalg.slogdet(R)[1]

            # Compute lower bound terms
            dict1 = self.block1.get_bound_terms(R, 
                                                logdet=logdetR, 
                                                inv=invR)
            dict2 = self.block2.get_bound_terms(invR.T, 
                                                logdet=-logdetR, 
                                                inv=R.T)

            if not gradient:
                dict1.update(dict2)
                return dict1
            else:
                terms = dict1[0].copy()
                terms = terms.update(dict2[0])
                grad = dict1[1].copy()
                grad = grad.update(dict2[1])
                return (terms, grad)

        def get_true_bound_terms():
            nodes = set(self.block1.nodes()) | set(self.block2.nodes())
            D = {}
            # TODO/FIXME: Also compute bound for child nodes as they could be
            # affected in practice although they shouldn't. Just checking that.
            for node in nodes:
                L = node.lower_bound_contribution()
                D[node] = L
            return D


        self.block1.setup()
        self.block2.setup()
        
        if check_gradient:
            R = np.random.randn(self.D, self.D)
            err = utils.optimize.check_gradient(cost, np.ravel(R), 
                                                verbose=False)
            if err > 1e-5:
                warnings.warn("Rotation gradient has relative error %g" % err)

        # Initial rotation is identity matrix
        r0 = np.ravel(np.identity(self.D))

        (cost_begin, _) = cost(r0)
        if check_bound:
            bound_terms_begin = get_bound_terms(r0)
            true_bound_terms_begin = get_true_bound_terms()

        # Run optimization
        r = utils.optimize.minimize(cost, r0, maxiter=maxiter, verbose=verbose)

        (cost_end, _) = cost(r)
        if check_bound:
            bound_terms_end = get_bound_terms(r)

        # Apply the optimal rotation
        R = np.reshape(r, (self.D,self.D))
        invR = np.linalg.inv(R)
        logdetR = np.linalg.slogdet(R)[1]
        self.block1.rotate(R, inv=invR, logdet=logdetR)
        self.block2.rotate(invR.T, inv=R.T, logdet=-logdetR)

        # Check that the cost function and the true lower bound changed equally
        cost_change = cost_end - cost_begin
        
        # Check that we really have improved the bound.
        if cost_change > 0:
            warnings.warn("Rotation optimization made the cost function worse "
                          "by %g. Probably a bug in the gradient of the "
                          "rotation functions."
                          % (cost_change,))
                
        if check_bound:
            true_bound_terms_end = get_true_bound_terms()
            bound_change = 0
            for node in bound_terms_begin.keys():
                node_bound_change = (bound_terms_end[node] 
                                    - bound_terms_begin[node])
                bound_change += node_bound_change
                true_node_bound_change = 0
                try:
                    true_node_bound_change += (true_bound_terms_end[node] 
                                               - true_bound_terms_begin[node])
                except KeyError:
                    raise Exception("The node %s is part of the "
                                    "transformation but not part of the "
                                    "model. Check your VB construction." 
                                    % node.name)
                if not np.allclose(node_bound_change, true_node_bound_change):
                    warnings.warn("Rotation cost function is not consistent "
                                  "with the true lower bound for node %s. "
                                  "Bound changed %g but optimized function "
                                  "changed %g."  
                                  % (node.name,
                                     true_node_bound_change,
                                     node_bound_change))

            # Check that we really have improved the bound.
            # TODO/FIXME: Also compute bound for child nodes as they could be
            # affected in practice although they shouldn't. Just checking that.
            if bound_change < 0:
                warnings.warn("Rotation made the true lower bound worse by %g. "
                              "Probably a bug in the rotation functions."
                              % (bound_change,))
                

class RotateGaussian():

    def __init__(self, X):
        self.X = X

    def rotate(self, R, inv=None, logdet=None):
        self.X.rotate(R, inv=inv, logdet=logdet)

    def setup(self):
        """
        This method should be called just before optimization.
        """
        
        mask = self.X.mask[...,np.newaxis,np.newaxis]

        # Number of plates
        self.N = self.X.plates[0] #np.sum(mask)

        # Compute the sum <XX> over plates
        self.XX = utils.utils.sum_multiply(self.X.get_moments()[1],
                                           mask,
                                           axis=(-1,-2),
                                           sumaxis=False,
                                           keepdims=False)
        # Parent's moments
        self.Lambda = self.X.parents[1].get_moments()[0]

    def _compute_bound(self, R, logdet=None, inv=None, gradient=False):
        
        """
        Rotate q(X) as X->RX: q(X)=N(R*mu, R*Cov*R')

        Assume:
        :math:`p(\mathbf{X}) = \prod^M_{m=1} 
               N(\mathbf{x}_m|0, \mathbf{\Lambda})`
        """

        # TODO/FIXME: X and alpha should NOT contain observed values!! Check
        # that.

        # TODO/FIXME: Allow non-zero prior mean!

        # Assume constant mean and precision matrix over plates..

        # Compute rotated moments
        XX_R = dot(R, self.XX, R.T)

        inv_R = inv
        logdet_R = logdet

        # Compute entropy H(X)
        logH_X = utils.random.gaussian_entropy(-2*self.N*logdet_R, 
                                               0)

        # Compute <log p(X)>
        logp_X = utils.random.gaussian_logpdf(np.vdot(XX_R, self.Lambda),
                                              0,
                                              0,
                                              0,
                                              0)

        # Compute the bound
        if terms:
            bound = {self.X: bound}
        else:
            bound = logp_X + logH_X

        if not gradient:
            return bound

        # Compute dH(X)
        dlogH_X = utils.random.gaussian_entropy(-2*self.N*inv_R.T,
                                                0)

        # Compute d<log p(X)>
        dXX = 2*dot(self.Lambda, R, self.XX)
        dlogp_X = utils.random.gaussian_logpdf(dXX,
                                               0,
                                               0,
                                               0,
                                               0)

        if terms:
            d_bound = {self.X: dlogp_X + dlogH_X}
        else:
            d_bound = dlogp_X + dlogH_X

        return (bound, d_bound)


    def bound(self, R, logdet=None, inv=None):
        return self._compute_bound(R, 
                                   logdet=logdet,
                                   inv=inv,
                                   gradient=True)

    def get_bound_terms(self, R, logdet=None, inv=None):
        return self._compute_bound(R, 
                                   logdet=logdet,
                                   inv=inv,
                                   gradient=False,
                                   terms=True)
        
    def nodes(self):
        return [self.X]


    
def covariance_to_variance(C, ndim=1, covariance_axis=None):
    # Force None to empty list
    if covariance_axis is None:
        covariance_axis = []

    # Force a list from integer
    if isinstance(covariance_axis, int):
        covariance_axis = [covariance_axis]

    # Force positive axis indices
    covariance_axis = [axis + ndim if axis < 0 else axis 
                       for axis in covariance_axis]
    
    # Make a set of the axes
    covariance_axis = set(covariance_axis)

    keys = [i+ndim if i in covariance_axis else i for i in range(ndim)]
    keys += [i+2*ndim if i in covariance_axis else i for i in range(ndim)]
    out_keys = sorted(list(set(keys)))

    return np.einsum(C, [Ellipsis]+keys, [Ellipsis]+out_keys)

def sum_to_plates(V, plates_to, plates_from=None, ndim=0):
    if ndim == 0:
        if plates_from is not None:
            r = gaussian.Gaussian._plate_multiplier(plates_from,
                                                    np.shape(V))
        else:
            r = 1
        return r * utils.utils.sum_to_shape(V, plates_to)
    else:
        dims_V = np.shape(V)[-ndim:]
        plates_V = np.shape(V)[:-ndim]
        shape_to = tuple(plates_to) + dims_V
        if plates_from is not None:
            r = gaussian.Gaussian._plate_multiplier(plates_from, plates_V)
        else:
            r = 1
        return r * utils.utils.sum_to_shape(V, shape_to)

class RotateGaussianARD():
    """
    Class for computing the cost of rotating a Gaussian array with ARD prior.

    The model:

    alpha ~ N(a, b)
    X ~ N(mu, alpha)

    X can be an array (e.g., GaussianARD).

    Transform q(X) and q(alpha) by rotating X.

    Requirements:
    * X and alpha do not contain any observed values
    """
    def __init__(self, X, *alpha, axis=-1, precompute=False):
        """
        Precompute tells whether to compute some moments once in the setup
        function instead of every time in the bound function.  However, they are
        computed a bit differently in the bound function so it can be useful
        too. Precomputation is probably beneficial only when there are large
        axes that are not rotated (by R nor Q) and they are not contained in the
        plates of alpha, and the dimensions for R and Q are quite small.
        """
        
        self.precompute = precompute
        
        if len(alpha) == 0:
            alpha = X.parents[1]
            self.update_alpha = False
        elif len(alpha) == 1:
            alpha = alpha[0]
            self.update_alpha = True
        else:
            raise ValueError("Too many arguments")
        self.node_X = X
        self.node_alpha = alpha
        self.node_mu = X.parents[0]
        self.ndim = len(X.dims[0])

        # Force negative rotation axis indexing
        if not isinstance(axis, int):
            raise ValueError("Axis must be integer")
        if axis >= 0:
            axis -= self.ndim
        if axis < -self.ndim or axis >= 0:
            raise ValueError("Axis out of bounds")
        self.axis = axis


    def nodes(self):
        if self.update_alpha:
            return [self.node_X, self.node_alpha]
        else:
            return [self.node_X]

    def rotate(self, R, inv=None, logdet=None, Q=None):

        self.node_X.rotate(R, 
                           inv=inv, 
                           logdet=logdet, 
                           axis=self.axis)

        if self.plate_axis is not None:
            self.node_X.rotate_plates(Q, plate_axis=self.plate_axis)

        if self.update_alpha:
            self.node_alpha.update()

    def setup(self, plate_axis=None):
        """
        This method should be called just before optimization.

        For efficiency, sum over axes that are not in mu, alpha nor rotation.

        If using Q, set rotate_plates to True.
        """

        # Store the original plate_axis parameter for later use in other methods
        self.plate_axis = plate_axis

        # Manipulate the plate_axis parameter to suit the needs of this method
        if plate_axis is not None:
            if not isinstance(plate_axis, int):
                raise ValueError("Plate axis must be integer")
            if plate_axis >= 0:
                plate_axis -= len(self.node_X.plates)
            if plate_axis < -len(self.node_X.plates) or plate_axis >= 0:
                raise ValueError("Axis out of bounds")
            plate_axis -= self.ndim - 1 # Why -1? Because one axis is preserved!
                
        # Get the mean parameter. It will not be rotated.
        (mu, mumu) = self.node_mu.get_moments()
        # For simplicity, force mu to have the same shape as X
        (mu, mumu) = gaussian.reshape_gaussian_array(self.node_mu.dims[0],
                                                     self.node_X.dims[0],
                                                     mu,
                                                     mumu)

        (X, XX) = self.node_X.get_moments()

        # Take diagonal of covariances to variances for axes that are not in R
        # (and move those axes to be the last)
        XX = covariance_to_variance(XX,
                                    ndim=self.ndim,
                                    covariance_axis=self.axis)
        mumu = covariance_to_variance(mumu,
                                      ndim=self.ndim, 
                                      covariance_axis=self.axis)
        
        # Move axes of X and mu and compute their outer product
        X = utils.utils.moveaxis(X, self.axis, -1)
        mu = utils.utils.moveaxis(mu, self.axis, -1)
        Xmu = utils.linalg.outer(X, mu, ndim=1)
        D = np.shape(X)[-1]
        
        # Move axes of alpha related variables
        def safe_move_axis(x):
            if np.ndim(x) >= -self.axis:
                return utils.utils.moveaxis(x, self.axis, -1)
            else:
                return x[...,np.newaxis]
        if self.update_alpha:
            a = safe_move_axis(self.node_alpha.phi[1])
            a0 = safe_move_axis(self.node_alpha.parents[0].get_moments()[0])
            b0 = safe_move_axis(self.node_alpha.parents[1].get_moments()[0])
        else:
            alpha = safe_move_axis(self.node_alpha.get_moments()[0])

        # Move plates of alpha for R
        plates_alpha = list(self.node_alpha.plates)
        if len(plates_alpha) >= -self.axis:
            plate = plates_alpha.pop(self.axis)
            plates_alpha.append(plate)
        else:
            plates_alpha.append(1)
            
        plates_X = list(self.node_X.get_shape(0))
        plates_X.pop(self.axis)

        def sum_to_alpha(V):
            # TODO/FIXME: This could be improved so that it is not required to
            # explicitly repeat to alpha plates. Multiplying by ones was just a
            # simple bug fix.
            return sum_to_plates(V * np.ones(plates_alpha[:-1]+[1,1]),
                                 plates_alpha[:-1],
                                 ndim=2,
                                 plates_from=plates_X)
        
        if plate_axis is not None:
            # Move plate axis just before the rotated dimensions (which are
            # last)
            def safe_move_plate_axis(x, ndim):
                if np.ndim(x)-ndim >= -plate_axis:
                    return utils.utils.moveaxis(x, 
                                                plate_axis-ndim,
                                                -ndim-1)
                else:
                    inds = (Ellipsis,None) + ndim*(slice(None),)
                    return x[inds]
            X = safe_move_plate_axis(X, 1)
            mu = safe_move_plate_axis(mu, 1)
            XX = safe_move_plate_axis(XX, 2)
            mumu = safe_move_plate_axis(mumu, 2)
            if self.update_alpha:
                a = safe_move_plate_axis(a, 1)
                a0 = safe_move_plate_axis(a0, 1)
                b0 = safe_move_plate_axis(b0, 1)
            else:
                alpha = safe_move_plate_axis(alpha, 1)
            # Move plates of X and alpha
            plate = plates_X.pop(plate_axis)
            plates_X.append(plate)
            if len(plates_alpha) >= -plate_axis+1:
                plate = plates_alpha.pop(plate_axis-1)
            else:
                plate = 1
            plates_alpha = plates_alpha[:-1] + [plate] + plates_alpha[-1:]

            CovX = XX - utils.linalg.outer(X, X)
            self.CovX = sum_to_plates(CovX,
                                      plates_alpha[:-2],
                                      ndim=3,
                                      plates_from=plates_X[:-1])
            # Broadcast mumu to ensure shape
            mumu = np.ones(np.shape(XX)[-3:]) * mumu
            self.mumu = sum_to_alpha(mumu)

            if self.precompute:
                # Precompute some stuff for the gradient of plate rotation
                #
                # NOTE: These terms may require a lot of memory if alpha has the
                # same or almost the same plates as X.
                self.X_X = sum_to_plates(X[...,:,:,None,None] *
                                         X[...,None,None,:,:],
                                         plates_alpha[:-2],
                                         ndim=4,
                                         plates_from=plates_X[:-1])
                self.X_mu = sum_to_plates(X[...,:,:,None,None] *
                                          mu[...,None,None,:,:],
                                          plates_alpha[:-2],
                                          ndim=4,
                                          plates_from=plates_X[:-1])
            else:
                self.X = X
                self.mu = mu
                    
        else:
            # Sum axes that are not in the plates of alpha
            self.XX = sum_to_alpha(XX)
            self.mumu = sum_to_alpha(mumu)
            self.Xmu = sum_to_alpha(Xmu)
            
        
        if self.update_alpha:
            self.a = a
            self.a0 = a0
            self.b0 = b0
        else:
            self.alpha = alpha

        self.plates_X = plates_X
        self.plates_alpha = plates_alpha


    def _compute_bound(self, R, logdet=None, inv=None, Q=None, gradient=False, terms=False):
        """
        Rotate q(X) and q(alpha).

        Assume:
        p(X|alpha) = prod_m N(x_m|0,diag(alpha))
        p(alpha) = prod_d G(a_d,b_d)
        """

        #
        # Transform the distributions and moments
        #

        plates_alpha = self.plates_alpha
        plates_X = self.plates_X
        
        # Compute rotated second moment
        if self.plate_axis is not None:
            # The plate axis has been moved to be the last plate axis

            if Q is None:
                raise ValueError("Plates should be rotated but no Q give")

            # Transform covariance
            sumQ = np.sum(Q, axis=0)
            QCovQ = sumQ[:,None,None]**2 * self.CovX
            
            # Rotate plates
            if self.precompute:
                QX_QX = np.einsum('...kalb,...ik,...il->...iab', self.X_X, Q, Q)
                XX = QX_QX + QCovQ
                XX = sum_to_plates(XX,
                                   plates_alpha[:-1],
                                   ndim=2)
                Xmu = np.einsum('...kaib,...ik->...iab', self.X_mu, Q)
                Xmu = sum_to_plates(Xmu,
                                   plates_alpha[:-1],
                                   ndim=2)
            else:
                X = self.X
                mu = self.mu
                QX = np.einsum('...ik,...kj->...ij', Q, X)
                XX = (sum_to_plates(QCovQ,
                                    plates_alpha[:-1],
                                    ndim=2) +
                      sum_to_plates(utils.linalg.outer(QX, QX),
                                    plates_alpha[:-1],
                                    ndim=2,
                                    plates_from=plates_X))
                Xmu = sum_to_plates(utils.linalg.outer(QX, self.mu),
                                    plates_alpha[:-1],
                                    ndim=2,
                                    plates_from=plates_X)

            mumu = self.mumu
            D = np.shape(XX)[-1]
            logdet_Q = D * np.log(np.abs(sumQ))

        else:
            XX = self.XX
            mumu = self.mumu
            Xmu = self.Xmu
            logdet_Q = 0

        # Compute transformed moments
        mumu = np.einsum('...ii->...i', mumu)
        RXmu = np.einsum('...ik,...ki->...i', R, Xmu)
        RXX = np.einsum('...ik,...kj->...ij', R, XX)
        RXXR = np.einsum('...ik,...ik->...i', RXX, R)

        # <(X-mu) * (X-mu)'>_R
        XmuXmu = (RXXR - 2*RXmu + mumu)

        D = np.shape(R)[0]

        # Compute q(alpha)
        if self.update_alpha:
            # Parameters
            a0 = self.a0
            b0 = self.b0
            a = self.a
            b = b0 + 0.5*sum_to_plates(XmuXmu,
                                       plates_alpha,
                                       plates_from=None,
                                       ndim=0)
            # Some expectations
            alpha = a / b
            logb = np.log(b)
            logalpha = -logb # + const
            b0_alpha = b0 * alpha
            a0_logalpha = a0 * logalpha
        else:
            alpha = self.alpha
            logalpha = 0
        
        #
        # Compute the cost
        #

        def sum_plates(V, *plates):
            full_plates = utils.utils.broadcasted_shape(*plates)
            
            r = self.node_X._plate_multiplier(full_plates, np.shape(V))
            return r * np.sum(V)

        XmuXmu_alpha = XmuXmu * alpha

        if logdet is None:
            logdet_R = np.linalg.slogdet(R)[1]
            inv_R = np.linalg.inv(R)
        else:
            logdet_R = logdet
            inv_R = inv

        # Compute entropy H(X)
        logH_X = utils.random.gaussian_entropy(-2*sum_plates(logdet_R + logdet_Q,
                                                             plates_X),
                                               0)

        # Compute <log p(X|alpha)>
        logp_X = utils.random.gaussian_logpdf(sum_plates(XmuXmu_alpha,
                                                         plates_alpha[:-1] + [D]),
                                              0,
                                              0,
                                              sum_plates(logalpha,
                                                         plates_X + [D]),
                                              0)

        if self.update_alpha:

            # Compute entropy H(alpha)
            # This cancels out with the log(alpha) term in log(p(alpha))
            logH_alpha = 0

            # Compute <log p(alpha)>
            logp_alpha = utils.random.gamma_logpdf(sum_plates(b0_alpha,
                                                              plates_alpha),
                                                   0,
                                                   sum_plates(a0_logalpha,
                                                              plates_alpha),
                                                   0,
                                                   0)
        else:
            logH_alpha = 0
            logp_alpha = 0

        # Compute the bound
        if terms:
            bound = {self.node_X: logp_X + logH_X}
            if self.update_alpha:
                bound.update({self.node_alpha: logp_alpha + logH_alpha})
        else:
            bound = (0
            + logp_X
            + logp_alpha
            + logH_X
            + logH_alpha
                     )

        if not gradient:
            return bound

        #
        # Compute the gradient with respect R
        #

        plate_multiplier = self.node_X._plate_multiplier
        def sum_plates(V, plates):
            ones = np.ones(np.shape(R))
            r = plate_multiplier(plates, np.shape(V)[:-2])
            return r * utils.utils.sum_multiply(V, ones,
                                             axis=(-1,-2),
                                             sumaxis=False,
                                             keepdims=False)

        D_XmuXmu = 2*RXX - 2*gaussian.transpose_covariance(Xmu)

        DXmuXmu_alpha = np.einsum('...i,...ij->...ij', 
                                  alpha,
                                  D_XmuXmu)
        if self.update_alpha:
            D_b            = 0.5 * D_XmuXmu
            XmuXmu_Dalpha  = np.einsum('...i,...i,...i,...ij->...ij', 
                                       sum_to_plates(XmuXmu,
                                                     plates_alpha,
                                                     plates_from=None,
                                                     ndim=0), 
                                       alpha, 
                                       -1/b, 
                                       D_b)
            D_b0_alpha     = np.einsum('...i,...i,...i,...ij->...ij', 
                                       b0,
                                       alpha,
                                       -1/b,
                                       D_b)
            D_logb         = np.einsum('...i,...ij->...ij', 
                                       1/b,
                                       D_b)
            D_logalpha     = -D_logb
            D_a0_logalpha  = a0 * D_logalpha
        else:
            XmuXmu_Dalpha = 0
            D_logalpha = 0

        D_XmuXmu_alpha = DXmuXmu_alpha + XmuXmu_Dalpha
        D_logR         = inv_R.T
        
        
        # Compute dH(X)
        dlogH_X = utils.random.gaussian_entropy(-2*sum_plates(D_logR,
                                                              plates_X),
                                                0)

        # Compute d<log p(X|alpha)>
        dlogp_X = utils.random.gaussian_logpdf(sum_plates(D_XmuXmu_alpha,
                                                          plates_alpha[:-1]),
                                               0,
                                               0,
                                               (sum_plates(D_logalpha,
                                                           plates_X)
                                                * plate_multiplier((D,),
                                                                   plates_alpha[-1:])),
                                               0)

        if self.update_alpha:

            # Compute dH(alpha)
            # This cancels out with the log(alpha) term in log(p(alpha))
            dlogH_alpha = 0

            # Compute d<log p(alpha)>
            dlogp_alpha = utils.random.gamma_logpdf(sum_plates(D_b0_alpha,
                                                               plates_alpha[:-1]),
                                                    0,
                                                    sum_plates(D_a0_logalpha,
                                                               plates_alpha[:-1]),
                                                    0,
                                                    0)
        else:
            dlogH_alpha = 0
            dlogp_alpha = 0

        if terms:
            raise NotImplementedError()
            dR_bound = {self.node_X: dlogp_X + dlogH_X}
            if self.update_alpha:
                dR_bound.update({self.node_alpha: dlogp_alpha + dlogH_alpha})
        else:
            dR_bound = (0*dlogp_X
            + dlogp_X
            + dlogp_alpha
            + dlogH_X
            + dlogH_alpha
                        )

        if self.plate_axis is None:
            return (bound, dR_bound)

        #
        # Compute the gradient with respect to Q (if Q given)
        #

        # Some pre-computations
        Q_RCovR = np.einsum('...ik,...kl,...il,...->...i', 
                            R, 
                            self.CovX,
                            R, 
                            sumQ)
        if self.precompute:
            Xr_rX = np.einsum('...abcd,...jb,...jd->...jac', 
                               self.X_X, 
                               R, 
                               R)
            QXr_rX = np.einsum('...akj,...ik->...aij', 
                               Xr_rX, 
                               Q)
            RX_mu = np.einsum('...jk,...akbj->...jab', 
                              R, 
                              self.X_mu)

        else:
            RX = np.einsum('...ik,...k->...i', R, X)
            QXR = np.einsum('...ik,...kj->...ij', Q, RX)
            QXr_rX = np.einsum('...ik,...jk->...kij', QXR, RX)
            RX_mu = np.einsum('...ik,...jk->...kij', RX, mu)

            QXr_rX = sum_to_plates(QXr_rX,
                                   plates_alpha[:-2],
                                   ndim=3,
                                   plates_from=plates_X[:-1])
            RX_mu = sum_to_plates(RX_mu,
                                  plates_alpha[:-2],
                                  ndim=3,
                                  plates_from=plates_X[:-1])
        
        def psi(v):
            """
            Compute: d/dQ 1/2*trace(diag(v)*<(X-mu)*(X-mu)>)

            = Q*<X>'*R'*diag(v)*R*<X> + ones * Q diag( tr(R'*diag(v)*R*Cov) ) 
              + mu*diag(v)*R*<X>
            """

            # Precompute all terms to plates_alpha because v has shape
            # plates_alpha.

            # Gradient of 0.5*v*<x>*<x>
            v_QXrrX = np.einsum('...kij,...ik->...ij', QXr_rX, v)

            # Gradient of 0.5*v*Cov
            Q_tr_R_v_R_Cov = np.einsum('...k,...k->...', Q_RCovR, v)[...,None,:]

            # Gradient of mu*v*x
            mu_v_R_X = np.einsum('...ik,...kji->...ij', v, RX_mu)

            return v_QXrrX + Q_tr_R_v_R_Cov - mu_v_R_X

        def sum_plates(V, plates):
            ones = np.ones(np.shape(Q))
            r = self.node_X._plate_multiplier(plates,
                                              np.shape(V)[:-2])

            return r * utils.utils.sum_multiply(V, ones,
                                                axis=(-1,-2),
                                                sumaxis=False,
                                                keepdims=False)

        if self.update_alpha:
            D_logb = psi(1/b)
            XX_Dalpha = -psi(alpha/b * sum_to_plates(XmuXmu, plates_alpha))
            D_logalpha = -D_logb
        else:
            XX_Dalpha = 0
            D_logalpha = 0
        DXX_alpha = 2*psi(alpha)
        D_XX_alpha = DXX_alpha + XX_Dalpha
        D_logdetQ = D / sumQ
        N = np.shape(Q)[-1]

        # Compute dH(X)
        dQ_logHX = utils.random.gaussian_entropy(-2*sum_plates(D_logdetQ,
                                                               plates_X[:-1]),
                                                 0)

        # Compute d<log p(X|alpha)>
        dQ_logpX = utils.random.gaussian_logpdf(sum_plates(D_XX_alpha,
                                                           plates_alpha[:-2]),
                                                0,
                                                0,
                                                (sum_plates(D_logalpha,
                                                            plates_X[:-1])
                                                 * plate_multiplier((N,D),
                                                                    plates_alpha[-2:])),
                                                0)

        if self.update_alpha:

            D_alpha = -psi(alpha/b)
            D_b0_alpha = b0 * D_alpha
            D_a0_logalpha = a0 * D_logalpha

            # Compute dH(alpha)
            # This cancels out with the log(alpha) term in log(p(alpha))
            dQ_logHalpha = 0

            # Compute d<log p(alpha)>
            dQ_logpalpha = utils.random.gamma_logpdf(sum_plates(D_b0_alpha,
                                                                plates_alpha[:-2]),
                                                     0,
                                                     sum_plates(D_a0_logalpha,
                                                                plates_alpha[:-2]),
                                                     0,
                                                     0)
        else:

            dQ_logHalpha = 0
            dQ_logpalpha = 0

        if terms:
            raise NotImplementedError()
            dQ_bound = {self.node_X: dQ_logpX + dQ_logHX}
            if self.update_alpha:
                dQ_bound.update({self.node_alpha: dQ_logpalpha + dQ_logHalpha})
        else:
            dQ_bound = (0*dQ_logpX
            + dQ_logpX
            + dQ_logpalpha
            + dQ_logHX
            + dQ_logHalpha
                        )
        return (bound, dR_bound, dQ_bound)



    def bound(self, R, logdet=None, inv=None, Q=None):
        return self._compute_bound(R, 
                                   logdet=logdet, 
                                   inv=inv, 
                                   Q=Q,
                                   gradient=True)
            
    def get_bound_terms(self, R, logdet=None, inv=None, Q=None):
        return self._compute_bound(R, 
                                   logdet=logdet, 
                                   inv=inv, 
                                   Q=Q,
                                   gradient=False,
                                   terms=True)


    
class RotateGaussianMarkovChain():
    """
    Assume the following model.

    Constant, unit isotropic innovation noise. Unit variance only?

    Maybe: Assume innovation noise with unit variance? Would it help make this
    function more general with respect to A.

    TODO: Allow constant A or not rotating A.

    :math:`A` may vary in time.
    
    Shape of A: (N,D,D)
    Shape of AA: (N,D,D,D)

    No plates for X.
    """

    def __init__(self, X, *args):
        self.X_node = X
        self.A_node = X.parents[2]

        if len(args) == 0:
            raise NotImplementedError()
        elif len(args) == 1:
            self.A_rotator = args[0]
        else:
            raise ValueError("Wrong number of arguments")
        
        self.N = X.dims[0][0]

    def nodes(self):
        return [self.X_node] + self.A_rotator.nodes()

    def rotate(self, R, inv=None, logdet=None):
        if inv is None:
            inv = np.linalg.inv(R)
        if logdet is None:
            logdet = np.linalg.slogdet(R)[1]
            
        self.X_node.rotate(R, inv=inv, logdet=logdet)
        self.A_rotator.rotate(inv.T, inv=R.T, logdet=-logdet, Q=R)

    def _computations_for_A_and_X(self, XpXn, XpXp):
        # Get moments of A (and make sure they include time axis)
        (A, AA) = self.A_node.get_moments()
        A = utils.utils.atleast_nd(A, 3)
        AA = utils.utils.atleast_nd(AA, 4)
        CovA = AA - A[...,:,np.newaxis]*A[...,np.newaxis,:]

        #
        # Expectations with respect to A and X
        #

        # Compute: \sum_n <A_n> <x_{n-1} x_n^T>
        A_XpXn = (utils.utils.sum_multiply(A[...,:,:,None],
                                           XpXn[...,None,:,:],
                                           axis=(-3,-1),
                                           sumaxis=False) *
                  self.X_node._plate_multiplier(self.X_node.plates,
                                                np.shape(A)[:-3],
                                                np.shape(XpXn)[:-3]))

        # Compute: \sum_n <A_n> <x_{n-1} x_{n-1}^T> <A_n>^T
        A_XpXp = np.einsum('...ik,...kj->...ij', A, XpXp)
        A_XpXp_A = (utils.utils.sum_multiply(A_XpXp[...,:,None,:],
                                             A[...,None,:,:],
                                             axis=(-3,-2),
                                             sumaxis=False) *
                    self.X_node._plate_multiplier(self.X_node.plates,
                                                  np.shape(A)[:-3],
                                                  np.shape(A_XpXp)[:-3]))

        # Compute: \sum_n tr(CovA_n <x_{n-1} x_{n-1}^T>)
        CovA_XpXp = (utils.utils.sum_multiply(CovA,
                                              XpXp[...,None,:,:],
                                              axis=(-3,),
                                              sumaxis=False) *
                     self.X_node._plate_multiplier(self.X_node.plates,
                                                   np.shape(CovA)[:-4],
                                                   np.shape(XpXp)[:-3]))
        
        return (A_XpXn, A_XpXp_A, CovA_XpXp)

    def setup(self):
        """
        This method should be called just before optimization.
        """
        
        # Get moments of X
        (X, XnXn, XpXn) = self.X_node.get_moments()

        # TODO/FIXME: Sum to plates of A/CovA
        XpXp = XnXn[...,:-1,:,:]

        #
        # Expectations with respect to X
        #
        
        self.X0 = X[...,0,:]
        self.X0X0 = XnXn[...,0,:,:]
        #self.XnXn = np.sum(XnXn[...,1:,:,:], axis=-3)
        self.XnXn = sum_to_plates(XnXn[...,1:,:,:],
                                  (),
                                  plates_from=self.X_node.plates + (self.N-1,),
                                  ndim=2)

        # Get moments of the fixed parameter nodes
        mu = self.X_node.parents[0].get_moments()[0]
        self.Lambda = self.X_node.parents[1].get_moments()[0]
        self.Lambda_mu_X0 = utils.linalg.outer(np.einsum('...ik,...k->...i',
                                                         self.Lambda,
                                                         mu),
                                               self.X0)
        self.Lambda_mu_X0 = sum_to_plates(self.Lambda_mu_X0,
                                          (),
                                          plates_from=self.X_node.plates,
                                          ndim=2)

        #
        # Prepare the rotation for A
        #

        (self.A_XpXn, 
         self.A_XpXp_A, 
         self.CovA_XpXp) = self._computations_for_A_and_X(XpXn, XpXp)

        
        self.A_rotator.setup(plate_axis=-1)

        # Innovation noise is assumed to be I
        #self.v = self.X_node.parents[3].get_moments()[0]

    def _compute_bound(self, R, logdet=None, inv=None, gradient=False, terms=False):
        """
        Rotate q(X) as X->RX: q(X)=N(R*mu, R*Cov*R')

        Assume:
        :math:`p(\mathbf{X}) = \prod^M_{m=1} 
               N(\mathbf{x}_m|0, \mathbf{\Lambda})`

        Assume unit innovation noise covariance.
        """

        # TODO/FIXME: X and alpha should NOT contain observed values!! Check
        # that.

        # Assume constant mean and precision matrix over plates..

        if inv is None:
            invR = np.linalg.inv(R)
        else:
            invR = inv

        if logdet is None:
            logdetR = np.linalg.slogdet(R)[1]
        else:
            logdetR = logdet

        # Transform moments of X and A:
        
        Lambda_R_X0X0 = sum_to_plates(dot(self.Lambda, R, self.X0X0),
                                      (),
                                      plates_from=self.X_node.plates,
                                      ndim=2)
        R_XnXn = dot(R, self.XnXn)
        RA_XpXp_A = dot(R, self.A_XpXp_A)
        sumr = np.sum(R, axis=0)
        R_CovA_XpXp = sumr * self.CovA_XpXp

        # Compute entropy H(X)
        M = self.N*np.prod(self.X_node.plates) # total number of rotated vectors
        logH_X = utils.random.gaussian_entropy(-2 * M * logdetR, 
                                               0)

        # Compute <log p(X)>
        yy = tracedot(R_XnXn, R.T) + tracedot(Lambda_R_X0X0, R.T)
        yz = tracedot(dot(R,self.A_XpXn),R.T) + tracedot(self.Lambda_mu_X0, R.T)
        zz = tracedot(RA_XpXp_A, R.T) + np.einsum('...k,...k->...',
                                                  R_CovA_XpXp,
                                                  sumr)
        logp_X = utils.random.gaussian_logpdf(yy,
                                              yz,
                                              zz,
                                              0,
                                              0)

        # Compute dH(X)
        M = self.N*np.prod(self.X_node.plates) # total number of rotated vectors
        dlogH_X = utils.random.gaussian_entropy(-2 * M * invR.T,
                                                0)

        # Compute the bound
        if terms:
            bound = {self.X_node: logp_X + logH_X}
        else:
            bound = logp_X + logH_X

        if not gradient:
            return bound
        
        # Compute d<log p(X)>
        dyy = 2 * (R_XnXn + Lambda_R_X0X0)
        dyz = dot(R, self.A_XpXn + self.A_XpXn.T) + self.Lambda_mu_X0
        dzz = 2 * (RA_XpXp_A + R_CovA_XpXp)
        dlogp_X = utils.random.gaussian_logpdf(dyy,
                                               dyz,
                                               dzz,
                                               0,
                                               0)

        if terms:
            d_bound = {self.X_node: dlogp_X + dlogH_X}
        else:
            d_bound = (0*dlogp_X
                       + dlogp_X
                       + dlogH_X
                       )

        return (bound, d_bound)

    
    def bound(self, R, logdet=None, inv=None):

        if inv is None:
            inv = np.linalg.inv(R)
        if logdet is None:
            logdet = np.linalg.slogdet(R)[1]
            
        (bound_X, d_bound_X) = self._compute_bound(R,
                                                   logdet=logdet,
                                                   inv=inv,
                                                   gradient=True)
        
        # Compute cost and gradient from A
        (bound_A, dR_bound_A, dQ_bound_A) = self.A_rotator.bound(inv.T, 
                                                                 inv=R.T,
                                                                 logdet=-logdet,
                                                                 Q=R)
        dR_bound_A = -dot(inv.T, dR_bound_A.T, inv.T)

        # Compute the bound
        bound = bound_X + bound_A
        d_bound = d_bound_X + dR_bound_A + dQ_bound_A

        return (bound, d_bound)

    def get_bound_terms(self, R, logdet=None, inv=None):

        if inv is None:
            inv = np.linalg.inv(R)
        if logdet is None:
            logdet = np.linalg.slogdet(R)[1]
            
        terms_A = self.A_rotator.get_bound_terms(inv.T, 
                                                 inv=R.T,
                                                 logdet=-logdet,
                                                 Q=R)
        
        terms_X = self._compute_bound(R,
                                      logdet=logdet,
                                      inv=inv,
                                      gradient=False,
                                      terms=True)

        terms_X.update(terms_A)

        return terms_X

    
class RotateVaryingMarkovChain(RotateGaussianMarkovChain):
    """
    Assume the following model.

    Constant, unit isotropic innovation noise.

    :math:`A_n = \sum_k B_k s_{kn}`
    
    Gaussian B: (1,D) x (D,K)
    Gaussian S: (N,1) x (K)
    MC X:          () x (N+1,D)

    No plates for X.
    """

    def __init__(self, X, B, S, B_rotator):
        self.X_node = X
        self.B_node = B
        self.S_node = S
        self.B_rotator = B_rotator

        if len(S.plates) > 0 and S.plates[-1] > 1:
            raise ValueError("The length of the last plate of S must be 1.")
        if len(B.plates) > 1 and B.plates[-2] > 1:
            raise ValueError("The length of the last plate of B must be 1.")

        if len(S.dims[0]) != 1:
            raise ValueError("S should have exactly one variable axis")
        if len(B.dims[0]) != 2:
            raise ValueError("B should have exactly two variable axes")

        super().__init__(X, B_rotator)

    def _computations_for_A_and_X(self, XpXn, XpXp):

        # Get moments of B and S
        (B, BB) = self.B_node.get_moments()
        CovB = BB - B[...,:,:,None,None]*B[...,None,None,:,:]
        
        u_S = self.S_node.get_moments()
        S = u_S[0]
        SS = u_S[1]

        #
        # Expectations with respect to A and X
        #

        # TODO/FIXME: If S and B have overlapping plates, then these will give
        # wrong results, because those plates of S are summed before multiplying
        # by the plates of B. There should be some "smart einsum" function which
        # would compute sum-multiplys intelligently given a number of inputs.
        
        # Compute: \sum_n <A_n> <x_{n-1} x_n^T>
        # Axes: (N, D, D, D, K)
        S_XpXn = utils.utils.sum_multiply(S[...,None,None,:],
                                          XpXn[...,:,None,:,:,None],
                                          axis=(-3,-2,-1),
                                          sumaxis=False)
        A_XpXn = utils.utils.sum_multiply(B[...,:,:,None,:],
                                          S_XpXn[...,:,:,:],
                                          axis=(-4,-2),
                                          sumaxis=False)

        # Compute: \sum_n <A_n> <x_{n-1} x_{n-1}^T> <A_n>^T
        # Axes: (N, D, D, D, K, D, K)
        SS_XpXp = utils.utils.sum_multiply(SS[...,None,:,None,:],
                                           XpXp[...,None,:,None,:,None],
                                           axis=(-4,-3,-2,-1),
                                           sumaxis=False)
        B_SS_XpXp = utils.utils.sum_multiply(B[...,:,:,:,None,None],
                                             SS_XpXp[...,:,:,:,:],
                                             axis=(-4,-3),
                                             sumaxis=True)
        A_XpXp_A = utils.utils.sum_multiply(B_SS_XpXp[...,:,None,:,:],
                                            B[...,None,:,:,:],
                                            axis=(-4,-3),
                                            sumaxis=False)

        # Compute: \sum_n tr(CovA_n <x_{n-1} x_{n-1}^T>)
        # Axes: (D,D,K,D,K)
        CovA_XpXp = utils.utils.sum_multiply(CovB,
                                             SS_XpXp,
                                             axis=(-5,),
                                             sumaxis=False)

        return (A_XpXn, A_XpXp_A, CovA_XpXp)


class RotateSwitchingMarkovChain(RotateGaussianMarkovChain):
    """
    Assume the following model.

    Constant, unit isotropic innovation noise.

    :math:`A_n = B_{z_n}`
    
    Gaussian B:            (..., K,  D) x   (D)
    Categorical Z:         (...,   N-1) x   (K)
    GaussianMarkovChain X: (...)        x (N,D)

    No plates for X.
    """

    def __init__(self, X, B, Z, B_rotator):
        self.X_node = X
        self.B_node = B
        self.Z_node = Z._convert(CategoricalMoments)
        self.B_rotator = B_rotator

        (N,D) = self.X_node.dims[0]
        K = self.Z_node.dims[0][0]

        if len(self.Z_node.plates) == 0 and self.Z_node.plates[-1] != N-1:
            raise ValueError("Incorrect plate length in Z")
        if self.B_node.plates[-2:] != (K,D):
            raise ValueError("Incorrect plates in B")

        if len(self.Z_node.dims[0]) != 1:
            raise ValueError("Z should have exactly one variable axis")
        if len(self.B_node.dims[0]) != 1:
            raise ValueError("B should have exactly one variable axes")

        super().__init__(X, B_rotator)

    def _computations_for_A_and_X(self, XpXn, XpXp):

        # Get moments of B and Z
        (B, BB) = self.B_node.get_moments()
        CovB = BB - B[...,:,None]*B[...,None,:]
        
        u_Z = self.Z_node.get_moments()
        Z = u_Z[0]

        #
        # Expectations with respect to A and X
        #

        # Compute: \sum_n <A_n> <x_{n-1} x_n^T>
        Z_XpXn = np.einsum('...nij,...nk->...kij',
                           XpXn,
                           Z)
        A_XpXn = np.einsum('...kil,...klj->...ij',
                           B,
                           Z_XpXn)
        A_XpXn = sum_to_plates(A_XpXn,
                               (),
                               ndim=2,
                               plates_from=self.X_node.plates)
        
        # Compute: \sum_n <A_n> <x_{n-1} x_{n-1}^T> <A_n>^T
        Z_XpXp = np.einsum('...nij,...nk->...kij',
                           XpXp,
                           Z)
        B_Z_XpXp = np.einsum('...kil,...klj->...kij',
                             B,
                             Z_XpXp)
        A_XpXp_A = np.einsum('...kil,...kjl->...ij',
                             B_Z_XpXp,
                             B)
        A_XpXp_A = sum_to_plates(A_XpXp_A,
                                 (),
                                 ndim=2,
                                 plates_from=self.X_node.plates)
        
        # Compute: \sum_n tr(CovA_n <x_{n-1} x_{n-1}^T>)
        CovA_XpXp = np.einsum('...kij,...kdij->...d',
                              Z_XpXp,
                              CovB)
        CovA_XpXp = sum_to_plates(CovA_XpXp,
                                  (),
                                  ndim=1,
                                  plates_from=self.X_node.plates)


        return (A_XpXn, A_XpXp_A, CovA_XpXp)


class RotateMultiple():
    """
    Performs the same rotation for multiple nodes and combines the cost effect.
    """

    def __init__(self, *rotators):
        self.rotators = rotators

    def nodes(self):
        return [node
                for node in rotator.nodes()
                for rotator in self.rotators]

    def rotate(self, R, inv=None, logdet=None):
        for rotator in self.rotators:
            rotator.rotate(R, inv=inv, logdet=logdet)

    def setup(self):
        for rotator in self.rotators:
            rotator.setup()
    
    def bound(self, R, logdet=None, inv=None):
        bound = 0
        dbound = 0
        
        for rotator in self.rotators:
            (b, db) = rotator.bound(R, logdet=logdet, inv=inv)
            bound = bound + b
            dbound = dbound + db

        return (bound, dbound)

    def get_bound_terms(self, R, logdet=None, inv=None):
        return {node: terms 
                for (node, terms) in rotator.items()
                for rotator in self.rotators}
