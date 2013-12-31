'''

File: gaussian_process.py
Author: Hadayat Seddiqi
Date: 12-27-2013
Description: Gaussian process object class defined here with
             helper functions for initialization.

'''

import collections
import numpy as np
from scipy import spatial as spatial
from scipy import linalg as sln
from scipy import signal as spsig

# GP imports
import core
import inferences
import kernels
import likelihoods
import means

class GaussianProcess(object):
    """
    """
    def __init__(self, xTrain=None, yTrain=None, xTest=None, yTest=None, hyp=None,
                 fixHypLik=False, hypLik=None, cov='radial_basis', inf='exact', 
                 lik='gaussian', mean='zero'):
        self.xt = np.atleast_2d(xTrain)
        self.yt = np.atleast_2d(yTrain)
        self.xs = np.atleast_2d(xTest) if xTest is not None else None
        self.ys = np.atleast_2d(yTest) if yTest is not None else None
        # Check if we're being given a custom functions or a string
        # which corresponds to a built-in function
        if isinstance(cov, basestring):
            self.cov = eval('kernels.' + cov)
        else:
            self.cov = cov
        if isinstance(inf, basestring):
            self.inf = eval('inferences.' + inf)
        else:
            self.inf = inf
        if isinstance(lik, basestring):
            self.lik = eval('likelihoods.' + lik)
        else:
            self.lik = lik
        if isinstance(mean, basestring):
            self.mean = eval('means.' + mean)
        else:
            self.mean = mean
        self.hyp = hyp
        self.hypLik = hypLik
        self.fixHypLik = fixHypLik

    def train(self, hyp):
        """
        Return the negative log-likelihood of Z. This routine
        is used for optimization.
        """
        # Last parameter is always the noise variable
        if self.fixHypLik:
            hypLik = hyp[-1]
            hyp = hyp[0:-1]
            self.hypLik = hypLik
        else:
            hypLik = self.hypLik
        return self.inf(self.cov, self.mean, hyp, self.xt, self.yt, 
                        False, hypLik)

    def predict(self):
        x = self.xt
        xs = self.xs
        hyp = self.hyp
        hypLik = self.hypLik
        alpha, L, sW = self.inf(self.cov, self.mean, self.hyp, 
                                self.xt, self.yt, pred=True)
        ones = np.arange(alpha.shape[0], dtype=int) # Well, in MATLAB it's all ones
        # If for some reason L isn't provided
        if L is None:
            nz = np.where(alpha != 0)[0]  # this is really to determine sparsity
            K = self.cov(hyp, x[nz,:])
            L = sln.cholesky(np.eye(np.sum(nz)) + (sW*sW.T)*K)
        # Initialize some parameters
        isLtri = (np.tril(L,-1) == 0).all()
        nPoints = xs.shape[0]
        nProcessed = 0
        nBatch = 1000
        ymu = np.empty((nPoints,1))
        ys2 = np.empty((nPoints,1))
        fmu = np.empty((nPoints,1))
        fs2 = np.empty((nPoints,1))
        lp = np.empty((nPoints,1))
        # Loop through points
        while nProcessed < nPoints:
            rng = range(nProcessed, min(nProcessed+nBatch, nPoints))
            xsrng = np.matrix(xs[rng,:])
            xones = np.matrix(x[ones,:])
            Kdiag = self.cov(self.hyp, xsrng, diag=True)
            Koff = self.cov(self.hyp, xones, xsrng, diag=False)
            ms = self.mean(xsrng)
            N = alpha.shape[1]
            # Conditional mean fs|f, GPML Eqs. (2.25), (2.27)
            Fmu = np.tile(ms, (1,N)) + Koff.T*alpha[ones,:]
            # Predictive means, GPML Eqs. (2.25), (2.27)
            fmu[rng] = np.sum(Fmu, axis=1) / N
            # Calculate the predictive variances, GPML Eq. (2.26)
            if isLtri:
                # Use Cholesky parameters (L, alpha, sW) if L is triangular
                V = np.linalg.solve(L.T, 
                                    np.multiply(np.tile(sW, (1,len(rng))),Koff))
                # Predictive variances
                fs2[rng] = (Kdiag - 
                            np.matrix(np.multiply(V,V)).sum(axis=0).T)
            else:
                # Use alternative parameterization incase L is not triangular
                # Predictive variances
                fs2[rng] = (Kdiag + 
                            np.matrix(np.multiply(Koff,(L*Koff))).sum(axis=0).T)
            # No negative elements allowed (it's numerical noise)
            fs2[rng] = fs2[rng].clip(min=0)
            # In case of sampling (?)
            Fs2 = np.matrix(np.tile(fs2[rng], (1,N)))
            # 
            if self.ys is None:
                Lp, Ymu, Ys2 = self.lik(hyp, [], Fmu, Fs2, hypLik)
            else:
                Ys = np.tile(ys[rng], (1,N))
                Lp, Ymu, Ys2 = self.lik(hyp, Ys, Fmu, Fs2, hypLik)

            # Log probability
            lp[rng] = np.sum(Lp.reshape(Lp.size/N,N), axis=1) / N
            # Predictive mean ys|y
            ymu[rng] = np.sum(Ymu.reshape(Ymu.size/N,N), axis=1) / N
            # Predictive variance ys|y
            ys2[rng] = np.sum(Ys2.reshape(Ys2.size/N,N), axis=1) / N
            # Iterate batch
            nProcessed = rng[-1] + 1
        
        # return {'ymu': Ymu,
        #         'ys2': Ys2,
        #         'fmu': Fmu,
        #         'fs2': Fs2,
        #         'lp': None if self.ys is None else Lp,
        #         'post': [alpha, L, sW] }
        return {'ymu': ymu,
                'ys2': ys2,
                'fmu': fmu,
                'fs2': fs2,
                'lp': None if self.ys is None else lp,
                'post': [alpha, L, sW] }
