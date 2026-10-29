Source: https://raw.githubusercontent.com/numpy/numpy/v2.2.6/numpy/linalg/_linalg.py
Fetched: 2026-10-28

def svd(a, full_matrices=True, compute_uv=True, hermitian=False):
    """
    Singular Value Decomposition.

    When `a` is a 2D array, and ``full_matrices=False``, then it is
    factorized as ``u @ np.diag(s) @ vh = (u * s) @ vh``, where
    `u` and the Hermitian transpose of `vh` are 2D arrays with
    orthonormal columns and `s` is a 1D array of `a`'s singular
    values. When `a` is higher-dimensional, SVD is applied in
    stacked mode as explained below.

    Parameters
    ----------
    a : (..., M, N) array_like
        A real or complex array with ``a.ndim >= 2``.
    full_matrices : bool, optional
        If True (default), `u` and `vh` have the shapes ``(..., M, M)`` and
        ``(..., N, N)``, respectively.  Otherwise, the shapes are
        ``(..., M, K)`` and ``(..., K, N)``, respectively, where
        ``K = min(M, N)``.
    compute_uv : bool, optional
        Whether or not to compute `u` and `vh` in addition to `s`.  True
        by default.
    hermitian : bool, optional
        If True, `a` is assumed to be Hermitian (symmetric if real-valued),
        enabling a more efficient method for finding singular values.
        Defaults to False.

    Returns
    -------
    When `compute_uv` is True, the result is a namedtuple with the following
    attribute names:

    U : { (..., M, M), (..., M, K) } array
        Unitary array(s). The first ``a.ndim - 2`` dimensions have the same
        size as those of the input `a`. The size of the last two dimensions
        depends on the value of `full_matrices`. Only returned when
        `compute_uv` is True.
    S : (..., K) array
        Vector(s) with the singular values, within each vector sorted in
        descending order. The first ``a.ndim - 2`` dimensions have the same
        size as those of the input `a`.
    Vh : { (..., N, N), (..., K, N) } array
        Unitary array(s). The first ``a.ndim - 2`` dimensions have the same
        size as those of the input `a`. The size of the last two dimensions
        depends on the value of `full_matrices`. Only returned when
        `compute_uv` is True.

    Raises
    ------
    LinAlgError
        If SVD computation does not converge.

    See Also
    --------
    scipy.linalg.svd : Similar function in SciPy.
    scipy.linalg.svdvals : Compute singular values of a matrix.

    Notes
    -----
    The decomposition is performed using LAPACK routine ``_gesdd``.

    SVD is usually described for the factorization of a 2D matrix :math:`A`.
    The higher-dimensional case will be discussed below. In the 2D case, SVD is
    written as :math:`A = U S V^H`, where :math:`A = a`, :math:`U= u`,
    :math:`S= \\mathtt{np.diag}(s)` and :math:`V^H = vh`. The 1D array `s`
    contains the singular values of `a` and `u` and `vh` are unitary. The rows
    of `vh` are the eigenvectors of :math:`A^H A` and the columns of `u` are
    the eigenvectors of :math:`A A^H`. In both cases the corresponding
    (possibly non-zero) eigenvalues are given by ``s**2``.

    If `a` has more than two dimensions, then broadcasting rules apply, as
    explained in :ref:`routines.linalg-broadcasting`. This means that SVD is
    working in "stacked" mode: it iterates over all indices of the first
    ``a.ndim - 2`` dimensions and for each combination SVD is applied to the
    last two indices. The matrix `a` can be reconstructed from the
    decomposition with either ``(u * s[..., None, :]) @ vh`` or
    ``u @ (s[..., None] * vh)``. (The ``@`` operator can be replaced by the
    function ``np.matmul`` for python versions below 3.5.)

    If `a` is a ``matrix`` object (as opposed to an ``ndarray``), then so are
    all the return values.

    Examples
    --------
    >>> import numpy as np
    >>> rng = np.random.default_rng()
    >>> a = rng.normal(size=(9, 6)) + 1j*rng.normal(size=(9, 6))
    >>> b = rng.normal(size=(2, 7, 8, 3)) + 1j*rng.normal(size=(2, 7, 8, 3))


    Reconstruction based on full SVD, 2D case:

    >>> U, S, Vh = np.linalg.svd(a, full_matrices=True)
    >>> U.shape, S.shape, Vh.shape
    ((9, 9), (6,), (6, 6))
    >>> np.allclose(a, np.dot(U[:, :6] * S, Vh))
    True
    >>> smat = np.zeros((9, 6), dtype=complex)
    >>> smat[:6, :6] = np.diag(S)
    >>> np.allclose(a, np.dot(U, np.dot(smat, Vh)))
    True

    Reconstruction based on reduced SVD, 2D case:

    >>> U, S, Vh = np.linalg.svd(a, full_matrices=False)
    >>> U.shape, S.shape, Vh.shape
    ((9, 6), (6,), (6, 6))
    >>> np.allclose(a, np.dot(U * S, Vh))
    True
    >>> smat = np.diag(S)
    >>> np.allclose(a, np.dot(U, np.dot(smat, Vh)))
    True

    Reconstruction based on full SVD, 4D case:

    >>> U, S, Vh = np.linalg.svd(b, full_matrices=True)
    >>> U.shape, S.shape, Vh.shape
    ((2, 7, 8, 8), (2, 7, 3), (2, 7, 3, 3))
    >>> np.allclose(b, np.matmul(U[..., :3] * S[..., None, :], Vh))
    True
    >>> np.allclose(b, np.matmul(U[..., :3], S[..., None] * Vh))
    True

    Reconstruction based on reduced SVD, 4D case:

    >>> U, S, Vh = np.linalg.svd(b, full_matrices=False)
    >>> U.shape, S.shape, Vh.shape
    ((2, 7, 8, 3), (2, 7, 3), (2, 7, 3, 3))
    >>> np.allclose(b, np.matmul(U * S[..., None, :], Vh))
    True
    >>> np.allclose(b, np.matmul(U, S[..., None] * Vh))
    True

    """
    import numpy as _nx
    a, wrap = _makearray(a)

    if hermitian:
        # note: lapack svd returns eigenvalues with s ** 2 sorted descending,
        # but eig returns s sorted ascending, so we re-order the eigenvalues
        # and related arrays to have the correct order
        if compute_uv:
            s, u = eigh(a)
            sgn = sign(s)
            s = abs(s)
            sidx = argsort(s)[..., ::-1]
            sgn = _nx.take_along_axis(sgn, sidx, axis=-1)
            s = _nx.take_along_axis(s, sidx, axis=-1)
            u = _nx.take_along_axis(u, sidx[..., None, :], axis=-1)
            # singular values are unsigned, move the sign into v
            vt = transpose(u * sgn[..., None, :]).conjugate()
            return SVDResult(wrap(u), s, wrap(vt))
        else:
            s = eigvalsh(a)
            s = abs(s)
            return sort(s)[..., ::-1]

    _assert_stacked_2d(a)
    t, result_t = _commonType(a)

    m, n = a.shape[-2:]
    if compute_uv:
        if full_matrices:
            gufunc = _umath_linalg.svd_f
        else:
            gufunc = _umath_linalg.svd_s

        signature = 'D->DdD' if isComplexType(t) else 'd->ddd'
        with errstate(call=_raise_linalgerror_svd_nonconvergence,
                      invalid='call', over='ignore', divide='ignore',
                      under='ignore'):
            u, s, vh = gufunc(a, signature=signature)
        u = u.astype(result_t, copy=False)
        s = s.astype(_realType(result_t), copy=False)
        vh = vh.astype(result_t, copy=False)
        return SVDResult(wrap(u), s, wrap(vh))
    else:
        signature = 'D->d' if isComplexType(t) else 'd->d'
        with errstate(call=_raise_linalgerror_svd_nonconvergence,
                      invalid='call', over='ignore', divide='ignore',
                      under='ignore'):
            s = _umath_linalg.svd(a, signature=signature)
        s = s.astype(_realType(result_t), copy=False)
        return s
