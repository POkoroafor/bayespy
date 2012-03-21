import itertools
import numpy as np
#import scipy as sp
import scipy.sparse as sp # prefer CSC format
#import scipy.linalg.decomp_cholesky as decomp
#import scipy.linalg as linalg
#import scipy.special as special
#import matplotlib.pyplot as plt
#import time
#import profile
import scipy.spatial.distance as dist
import scikits.sparse.distance as spdist

import Nodes.ExponentialFamily as ef
import utils

import imp
imp.reload(spdist)
imp.reload(ef)
imp.reload(utils)

# Covariance matrices can be either arrays or matrices so be careful
# with products and powers! Use explicit multiply or dot instead of
# *-operator.


def gp_cov_se(D2, overwrite=False):
    if overwrite:
        K = D2
        K *= -0.5
        np.exp(K, out=K)
    else:
        K = np.exp(-0.5*D2)
    return K

def gp_cov_pp2(r, d, gradient=False):
    # Dimension dependent parameter
    j = np.floor(d/2) + 2 + 1

    # Polynomial coefficients
    a2 = j**2 + 4*j + 3
    a1 = 3*j + 6
    a0 = 3

    # Two parts of the covariance function
    k1 = (1-r) ** (j+2)
    k2 = (a2*r**2 + a1*r + 3)

    # The covariance function
    k = k1 * k2 / 3
        
    if gradient:
        # The gradient w.r.t. r
        dk = k * (j+2) / (r-1) + k1 * (2*a2*r + a1) / 3
        return (k, dk)
    else:
        return k

def gp_cov_delta(N):
    # TODO: Use sparse matrices here!
    if N > 0:
        #print('in gpcovdelta', N, sp.identity(N).shape)
        return sp.identity(N)
    else:
        # Sparse matrices do not allow zero-length dimensions
        return np.identity(N)
    #return np.identity(N)
    #return np.asmatrix(np.identity(N))
        

def squared_distance(x1, x2):
    ## # Reshape arrays to 2-D arrays
    ## sh1 = np.shape(x1)[:-1]
    ## sh2 = np.shape(x2)[:-1]
    ## d = np.shape(x1)[-1]
    ## x1 = np.reshape(x1, (-1,d))
    ## x2 = np.reshape(x2, (-1,d))
    # Compute squared Euclidean distance
    D2 = dist.cdist(x1, x2, metric='sqeuclidean')
    #D2 = np.asmatrix(D2)
    # Reshape the result
    #D2 = np.reshape(D2, sh1 + sh2)
    return D2

# General rule for the parameters for covariance functions:
#
# (value, [ [dvalue1, ...], [dvalue2, ...], [dvalue3, ...], ...])
#
# For instance,
#
# k = covfunc_se((1.0, []), (15, [ [1,update_grad] ]))
# K = k((x1, [ [dx1,update_grad] ]), (x2, []))
#
# Plain values are converted as:
# value  ->  (value, [])

def gp_standardize_input(x):
    if np.ndim(x) == 1:
        x = np.atleast_2d(x).T
        #x = np.asmatrix(x).T
    else:
        x = np.atleast_2d(x)
        # x = np.asmatrix(x)
    ## if np.ndim(x) == 0:
    ##     x = add_trailing_axes(x, 2)
    ## elif np.ndim(x) == 1:
    ##     x = add_trailing_axes(x, 1)
    return x

def gp_preprocess_inputs(*args):
    args = list(args)
    if len(args) < 1 or len(args) > 2:
        raise Exception("Number of inputs must be one or two")
    if len(args) == 2:
        if args[0] is args[1]:
            args[0] = gp_standardize_input(args[0])
            args[1] = args[0]
        else:
            args[1] = gp_standardize_input(args[1])
            args[0] = gp_standardize_input(args[0])
    else:
        args[0] = gp_standardize_input(args[0])
        
    return args

def covfunc_zeros(theta, *inputs, gradient=False):

    inputs = gp_preprocess_inputs(*inputs)

    # Compute distance and covariance matrix
    if len(inputs) == 1:
        # Only variance vector asked
        x = inputs[0]
        N = np.shape(x)[0]
        # TODO: Use sparse matrices!
        K = np.zeros(N)
        #K = np.asmatrix(np.zeros((N,1)))

    else:
        # Full covariance matrix asked
        x1 = inputs[0]
        x2 = inputs[1]
        # Number of inputs x1
        N1 = np.shape(x1)[0]
        N2 = np.shape(x2)[0]

        # TODO: Use sparse matrices!
        K = np.zeros((N1,N2))
        #K = np.asmatrix(np.zeros((N1,N2)))

    if gradient != False:
        return (K, [])
    else:
        return K

def covfunc_delta(theta, *inputs, gradient=False):

    amplitude = theta[0]

    if gradient:
        gradient_amplitude = gradient[0]
    else:
        gradient_amplitude = []

    inputs = gp_preprocess_inputs(*inputs)

    # Compute distance and covariance matrix
    if len(inputs) == 1:
        # Only variance vector asked
        x = inputs[0]
        N = np.shape(x)[0]
        K = np.ones(N) * amplitude**2

    else:
        # Full covariance matrix asked
        x1 = inputs[0]
        x2 = inputs[1]
        # Number of inputs x1
        N1 = np.shape(x1)[0]

        # x1 == x2?
        if x1 is x2:
            delta = True
            # Delta covariance
            #
            # FIXME: Broadcasting doesn't work with sparse matrices,
            # so turn the array into a scalar.
            K = gp_cov_delta(N1) * amplitude[0]**2
            #K = gp_cov_delta(N1).multiply(amplitude**2)
        else:
            delta = False
            # Number of inputs x2
            N2 = np.shape(x2)[0]
            # Zero covariance
            # TODO: Use sparse matrix here!
            if N1 > 0 and N2 > 0:
                K = sp.csc_matrix((N1,N2))
            else:
                K = np.zeros((N1,N2))
            #print('there')
            #K = np.zeros((N1,N2))

    # Gradient w.r.t. amplitude
    if gradient:
        for ind in range(len(gradient_amplitude)):
            # FIXME: Broadcasting doesn't work with sparse matrices,
            # so turn the array into a scalar.
            gradient_amplitude[ind] = K * (gradient_amplitude[ind][0] *
                                           (2/amplitude[0]))
            #gradient_amplitude[ind] = K.multiply(gradient_amplitude[ind] * (2/amplitude))
            ## gradient_amplitude[ind] = np.multiply(K,
            ##                                       gradient_amplitude[ind] * (2/amplitude))

    if gradient:
        return (K, gradient)
    else:
        return K

def covfunc_pp2(theta, *inputs, gradient=False):

    amplitude = theta[0]
    lengthscale = theta[1]

    if gradient:
        gradient_amplitude = gradient[0]
        gradient_lengthscale = gradient[1]
    else:
        gradient_amplitude = []
        gradient_lengthscale = []

    inputs = gp_preprocess_inputs(*inputs)

    # Compute covariance matrix
    if len(inputs) == 1:
        x = inputs[0]
        # Compute variance vector
        K = np.ones(np.shape(x)[:-1])
        K *= amplitude**2
        # Compute gradient w.r.t. lengthscale
        for ind in range(len(gradient_lengthscale)):
            gradient_lengthscale[ind] = np.zeros(np.shape(x)[:-1])
    
    else:
        x1 = inputs[0] / (lengthscale)
        if inputs[0] is inputs[1]:
            x2 = x1
            D2 = spdist.pdist(x1, 1.0, form="full", format="csc")
        else:
            x2 = inputs[1] / (lengthscale)
            D2 = spdist.cdist(x1, x2, 1.0, format="csc")
        r = np.sqrt(D2.data)

        # Compute (sparse) distance matrix

        #################
        ## OLD STUFF
        #x1 = inputs[0] / (lengthscale)
        #x2 = inputs[1] / (lengthscale)
        #D2 = squared_distance(x1, x2)
        #(i,j) = np.where(D2<1)
        #ij = np.vstack((i,j))
        #r = np.sqrt(D2[i,j])
        ##########################
        
        N1 = np.shape(x1)[0]
        N2 = np.shape(x2)[0]
        
        # Compute the covariances
        if gradient:
            (k, dk) = gp_cov_pp2(r, np.shape(x1)[-1], gradient=True)
        else:
            k = gp_cov_pp2(r, np.shape(x1)[-1])
        k *= amplitude**2
        # Compute gradient w.r.t. lengthscale
        if gradient:
            dk *= amplitude**2
            #print('her i aam', (N1, N2))
            for ind in range(len(gradient_lengthscale)):
                # FIXME: Check this gradient
                ## print(np.shape(lengthscale))
                ## print(np.shape(gradient_lengthscale[ind]),
                ##       gradient_lengthscale[ind].__class__)
                dk_i = (dk * r) * (-gradient_lengthscale[ind] / lengthscale)
                if N1 >= 1 and N2 >= 1:
                    ## gradient_lengthscale[ind] = sp.csc_matrix((dk_i, ij),
                    ##                                           shape=(N1,N2))
                    gradient_lengthscale[ind] = sp.csc_matrix((dk_i, D2.indices, D2.indptr),
                                                              shape=(N1,N2))
                else:
                    gradient_lengthscale[ind] = np.empty((N1,N2))
            
        # Form sparse covariance matrix
        if N1 >= 1 and N2 >= 1:
            ## K = sp.csc_matrix((k, ij), shape=(N1,N2))
            K = sp.csc_matrix((k, D2.indices, D2.indptr), shape=(N1,N2))
        else:
            K = np.empty((N1, N2))
        #print(K.__class__)

    # Gradient w.r.t. amplitude
    if gradient:
        for ind in range(len(gradient_amplitude)):
            # FIXME: Broadcasting doesn't work with sparse matrices,
            # so turn the array into a scalar.
            gradient_amplitude[ind] = K * (2 * gradient_amplitude[ind][0] / amplitude[0])
            ## gradient_amplitude[ind] = np.multiply(K,
            ##                                       2 * gradient_amplitude[ind] / amplitude)

    # Return values
    if gradient:
        return (K, gradient)
    else:
        return K


def covfunc_se(theta, *inputs, gradient=False):

    amplitude = theta[0]
    lengthscale = theta[1]

    if gradient:
        gradient_amplitude = gradient[0]
        gradient_lengthscale = gradient[1]
    else:
        gradient_amplitude = []
        gradient_lengthscale = []

    inputs = gp_preprocess_inputs(*inputs)

    # Compute covariance matrix
    if len(inputs) == 1:
        x = inputs[0]
        # Compute variance vector
        N = np.shape(x)[0]
        K = np.ones(N)
        np.multiply(K, amplitude**2, out=K)
        #K *= amplitude**2
        # Compute gradient w.r.t. lengthscale
        for ind in range(len(gradient_lengthscale)):
            # TODO: Use sparse matrices?
            gradient_lengthscale[ind] = np.zeros(N)
    else:
        x1 = inputs[0] / (lengthscale)
        x2 = inputs[1] / (lengthscale)
        # Compute distance matrix
        K = squared_distance(x1, x2)
        # Compute gradient partly
        if gradient:
            for ind in range(len(gradient_lengthscale)):
                dl = (lengthscale**-1) * gradient_lengthscale[ind]
                gradient_lengthscale[ind] = np.multiply(K, dl)
        # Compute covariance matrix
        gp_cov_se(K, overwrite=True)
        np.multiply(K, amplitude**2, out=K)
        #K *= amplitude**2
        # Compute gradient w.r.t. lengthscale
        if gradient:
            for ind in range(len(gradient_lengthscale)):
                gradient_lengthscale[ind] *= K

    # Gradient w.r.t. amplitude
    if gradient:
        for ind in range(len(gradient_amplitude)):
            da = 2 * gradient_amplitude[ind] / amplitude
            gradient_amplitude[ind] = np.multiply(K, da)

    #print('gradient in se', gradient)

    # Return values
    if gradient:
        return (K, gradient)
    else:
        return K


class CovarianceFunctionWrapper():
    def __init__(self, covfunc, *params):
        self.laskuri = 0
        # Parse parameter values and their gradients to separate lists
        self.covfunc = covfunc
        self.params = list(params)
        self.gradient_params = list()
        ## print(params)
        for ind in range(len(params)):
            if isinstance(params[ind], tuple):
                # Parse the value and the list of gradients from the
                # form:
                #  ([value, ...], [ [grad1, ...], [grad2, ...], ... ])
                self.gradient_params.append(params[ind][1])
                self.params[ind] = params[ind][0][0]
            else:
                # No gradients, parse from the form:
                #  [value, ...]
                self.gradient_params.append([])
                self.params[ind] = params[ind][0]

    def fixed_covariance_function(self, *inputs, gradient=False):

        # What if this is called several times??

        if gradient:

            #self.laskuri += 1
            #print('Laskuri in fixed_covariance_function')
            #print(self.laskuri)

            #print(self.gradient_params)

            grads = [[grad[0] for grad in self.gradient_params[ind]]
                     for ind in range(len(self.gradient_params))]

            #print('in covfuncwrap', grads)

            #print(self.gradient_params)

            ## (K, dK) = self.covfunc(self.params,
            ##                        *inputs,
            ##                        gradient=self.gradient_params)
            (K, dK) = self.covfunc(self.params,
                                   *inputs,
                                   gradient=grads)

            #print(self.gradient_params)
            # FIXME: This messes up self.gradient_params
            DK = []
            for ind in range(len(dK)):
                for (grad, dk) in zip(self.gradient_params[ind], dK[ind]):
                    #grad[0] = dk
                    DK += [ [dk] + grad[1:] ]

            #print(self.gradient_params)
            #print(DK)
            K = [K]
            #dK = []
            #for grad in self.gradient_params:
                #dK += grad

            #print(self.gradient_params)
            return (K, DK)

        else:
            K = self.covfunc(self.params,
                             *inputs,
                             gradient=False)
            #print(K.__class__)
            return [K]

class CovarianceFunction(ef.Node):


    def __init__(self, covfunc, *args, **kwargs):
        self.covfunc = covfunc

        params = list(args)
        for i in range(len(args)):
            # Check constant parameters
            if utils.is_numeric(args[i]):
                params[i] = ef.NodeConstant([np.asanyarray(args[i])],
                                            dims=[np.shape(args[i])])
                # TODO: Parameters could be constant functions? :)

        ef.Node.__init__(self, *params, dims=[(np.inf, np.inf)], **kwargs)

    def message_to_child(self, gradient=False):

        params = [parent.message_to_child(gradient=gradient) for parent in self.parents]
        covfunc = self.get_fixed_covariance_function(*params)
        return covfunc

    def get_fixed_covariance_function(self, *params):
        get_cov_func = CovarianceFunctionWrapper(self.covfunc, *params)
        return get_cov_func.fixed_covariance_function


    ## def covariance_function(self, *params):
    ##     # Parse parameter values and their gradients to separate lists
    ##     params = list(params)
    ##     gradient_params = list()
    ##     print(params)
    ##     for ind in range(len(params)):
    ##         if isinstance(params[ind], tuple):
    ##             # Parse the value and the list of gradients from the
    ##             # form:
    ##             #  ([value, ...], [ [grad1, ...], [grad2, ...], ... ])
    ##             gradient_params.append(params[ind][1])
    ##             params[ind] = params[ind][0][0]
    ##         else:
    ##             # No gradients, parse from the form:
    ##             #  [value, ...]
    ##             gradient_params.append([])
    ##             params[ind] = params[ind][0]

    ##     # This gradient_params changes mysteriously..
    ##     print('grad_params before')
    ##     if isinstance(self, SquaredExponential):
    ##         print(gradient_params)
            
    ##     def cov(*inputs, gradient=False):

    ##         if gradient:
    ##             print('grad_params after')
    ##             print(gradient_params)
    ##             grads = [[grad[0] for grad in gradient_params[ind]]
    ##                      for ind in range(len(gradient_params))]


    ##             print('CovarianceFunction.cov')
    ##             #if isinstance(self, SquaredExponential):
    ##                 #print(self.__class__)
    ##                 #print(grads)
    ##             (K, dK) = self.covfunc(params,
    ##                                    *inputs,
    ##                                    gradient=grads)

    ##             for ind in range(len(dK)):
    ##                 for (grad, dk) in zip(gradient_params[ind], dK[ind]):
    ##                     grad[0] = dk

    ##             K = [K]
    ##             dK = []
    ##             for grad in gradient_params:
    ##                 dK += grad
    ##             return (K, dK)
                    
    ##         else:
    ##             K = self.covfunc(params,
    ##                              *inputs,
    ##                              gradient=False)
    ##             return [K]

    ##     return cov


class Sum(CovarianceFunction):
    def __init__(self, *args, **kwargs):
        CovarianceFunction.__init__(self,
                                    None,
                                    *args,
                                    **kwargs)

    def get_fixed_covariance_function(self, *covfuncs):
        def cov(*inputs, gradient=False):
            K_sum = None
            if gradient:
                dK_sum = list()
            for k in covfuncs:
                if gradient:
                    (K, dK) = k(*inputs, gradient=gradient)
                    dK_sum += dK
                else:
                    K = k(*inputs, gradient=gradient)
                if K_sum is None:
                    K_sum = K[0]
                else:
                    try:
                        K_sum += K[0]
                    except:
                        # You have to do this way, for instance, if
                        # K_sum is sparse and K[0] is dense.
                        ## print(K_sum)
                        ## print(K[0])
                        ## print(np.shape(K_sum))
                        ## print(np.shape(K[0]))
                        ## print(K_sum.__class__)
                        ## print(K[0].__class__)
                        K_sum = K_sum + K[0]

            if gradient:
                #print('covsum', dK_sum)
                return ([K_sum], dK_sum)
            else:
                return [K_sum]

        return cov


class Delta(CovarianceFunction):
    def __init__(self, amplitude, **kwargs):
        CovarianceFunction.__init__(self,
                                    covfunc_delta,
                                    amplitude,
                                    **kwargs)

class Zeros(CovarianceFunction):
    def __init__(self, **kwargs):
        CovarianceFunction.__init__(self,
                                    covfunc_zeros,
                                    **kwargs)


class SquaredExponential(CovarianceFunction):
    def __init__(self, amplitude, lengthscale, **kwargs):
        CovarianceFunction.__init__(self,
                                    covfunc_se,
                                    amplitude,
                                    lengthscale,
                                    **kwargs)

class PiecewisePolynomial2(CovarianceFunction):
    def __init__(self, amplitude, lengthscale, **kwargs):
        CovarianceFunction.__init__(self,
                                    covfunc_pp2,
                                    amplitude,
                                    lengthscale,
                                    **kwargs)

# TODO: Rename to Blocks or Joint ?
class Multiple(CovarianceFunction):
    
    def __init__(self, covfuncs, **kwargs):
        self.d = len(covfuncs)
        #self.sparse = sparse
        parents = [covfunc for row in covfuncs for covfunc in row]
        CovarianceFunction.__init__(self,
                                    None,
                                    *parents,
                                    **kwargs)

    def get_fixed_covariance_function(self, *covfuncs):
        def cov(*inputs, gradient=False):

            # Computes the covariance matrix from blocks which all
            # have their corresponding covariance functions

            if len(inputs) < 2:
                # For one input, return the variance vector instead of
                # the covariance matrix
                x1 = inputs[0]
                # Collect variance vectors from the covariance
                # functions corresponding to the diagonal blocks
                K = [covfuncs[i*self.d+i](x1[i], gradient=gradient)[0]
                     for i in range(self.d)]
                # Form the variance vector from the collected vectors
                if gradient:
                    raise Exception('Gradient not yet implemented.')
                else:
                    ## print("in cov multiple")
                    ## for (k,kf) in zip(K,covfuncs):
                    ##     print(np.shape(k), k.__class__, kf)
                    #K = np.vstack(K)
                    K = np.concatenate(K)
            else:
                x1 = inputs[0]
                x2 = inputs[1]

                # Collect the covariance matrix (and possibly
                # gradients) from each block.
                #print('cov mat collection begins')
                K = [[covfuncs[i*self.d+j](x1[i], x2[j], gradient=gradient)
                      for j in range(self.d)]
                      for i in range(self.d)]
                #print('cov mat collection ends')

                # Remove matrices that have zero length dimensions?
                if gradient:
                    K = [[K[i][j]
                          for j in range(self.d)
                          if np.shape(K[i][j][0][0])[1] != 0]
                          for i in range(self.d)
                          if np.shape(K[i][0][0][0])[0] != 0]
                else:
                    K = [[K[i][j]
                          for j in range(self.d)
                          if np.shape(K[i][j][0])[1] != 0]
                          for i in range(self.d)
                          if np.shape(K[i][0][0])[0] != 0]
                n_blocks = len(K)

                # Check whether all blocks are sparse
                is_sparse = True
                for i in range(n_blocks):
                    for j in range(n_blocks):
                        if gradient:
                            A = K[i][j][0][0]
                        else:
                            A = K[i][j][0]
                        if not sp.issparse(A):
                            is_sparse = False

                if gradient:

                    ## Compute the covariance matrix and the gradients

                    # Create block matrices of zeros. This helps in
                    # computing the gradient.
                    if is_sparse:
                        # Empty sparse matrices. Some weird stuff here
                        # because sparse matrices can't have zero
                        # length dimensions.
                        #
                        Z = [[sp.csc_matrix(np.shape(K[i][j][0][0]))
                              for j in range(n_blocks)]
                              for i in range(n_blocks)]
                        ## Z = [[None
                        ##       for j in range(self.d)]
                        ##       for i in range(self.d)]
                        ## Z = [[sp.csc_matrix(np.shape(K[i][j][0][0]))
                        ##       for j in range(self.d)
                        ##       if np.shape(K[i][j][0])[1] != 0]
                        ##       for i in range(self.d)
                        ##       if np.shape(K[i][0][0])[0] != 0]
                              ## if (np.shape(K[i][j][0][0])[0] > 0 and
                              ##     np.shape(K[i][j][0][0])[1] > 0)
                              ## else
                              ## None
                              ## for j in range(self.d)]
                              ## for i in range(self.d)]
                    else:
                        # Empty dense matrices
                        Z = [[np.zeros(np.shape(K[i][j][0][0]))
                              for j in range(n_blocks)]
                              for i in range(n_blocks)]
                              ## for j in range(self.d)]
                              ## for i in range(self.d)]

                    # Compute gradients block by block
                    dK = list()
                    for i in range(n_blocks):
                        for j in range(n_blocks):
                    ## for i in range(self.d):
                    ##     for j in range(self.d):
                            # Store the zero block
                            z_old = Z[i][j]
                            # Go through the gradients for the (i,j)
                            # block
                            for dk in K[i][j][1]:
                                # Keep other blocks at zero and set
                                # the gradient to (i,j) block.  Form
                                # the matrix from blocks
                                if is_sparse:
                                    Z[i][j] = dk[0]
                                    dk[0] = sp.bmat(Z).tocsc()
                                else:
                                    if sp.issparse(dk[0]):
                                        Z[i][j] = dk[0].toarray()
                                    else:
                                        Z[i][j] = dk[0]
                                    dk[0] = np.asarray(np.bmat(Z))
                                # Append the computed gradient matrix
                                # to the list of gradients
                                dK.append(dk)
                            # Restore the zero block
                            Z[i][j] = z_old

                    ## Compute the covariance matrix but not the
                    ## gradients

                    if is_sparse:
                        # Form the full sparse covariance matrix from
                        # blocks.  Ignore blocks having a zero-length
                        # axis because sparse matrices consider zero
                        # length as an invalid shape (BUG IN SCIPY?).
                        K = [[K[i][j][0][0]
                              for j in range(n_blocks)]
                              for i in range(n_blocks)]
                        ## K = [[K[i][j][0][0]
                        ##       for j in range(self.d)
                        ##       if np.shape(K[i][j][0])[1] != 0]
                        ##       for i in range(self.d)
                        ##       if np.shape(K[i][0][0])[0] != 0]
                        K = sp.bmat(K).tocsc()
                    else:
                        # Form the full dense covariance matrix from
                        # blocks. Transform sparse blocks to dense
                        # blocks.
                        K = [[K[i][j][0][0]
                              if not sp.issparse(K[i][j][0][0]) else
                              K[i][j][0][0].toarray()
                              for j in range(n_blocks)]
                              for i in range(n_blocks)]
                              ## for j in range(self.d)]
                              ## for i in range(self.d)]
                        K = np.asarray(np.bmat(K))

                else:

                    ## Compute the covariance matrix but not the
                    ## gradients

                    if is_sparse:
                        # Form the full sparse covariance matrix from
                        # blocks.  Ignore blocks having a zero-length
                        # axis because sparse matrices consider zero
                        # length as an invalid shape (BUG IN SCIPY?).
                        K = [[K[i][j][0]
                              for j in range(n_blocks)]
                              for i in range(n_blocks)]
                        ## K = [[K[i][j][0]
                        ##       for j in range(self.d)
                        ##       if np.shape(K[i][j][0])[1] != 0]
                        ##       for i in range(self.d)
                        ##       if np.shape(K[i][0][0])[0] != 0]
                        K = sp.bmat(K).tocsc()
                    else:
                        # Form the full dense covariance matrix from
                        # blocks. Transform sparse blocks to dense
                        # blocks.
                        K = [[K[i][j][0]
                              if not sp.issparse(K[i][j][0]) else
                              K[i][j][0].toarray()
                              for j in range(n_blocks)]
                              for i in range(n_blocks)]
                              ## for j in range(self.d)]
                              ## for i in range(self.d)]
                        K = np.asarray(np.bmat(K))



            if gradient:
                return ([K], dK)
            else:
                return [K]

        return cov


