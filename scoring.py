try:
    from numba import njit, prange
    import numpy
    def wrap_numpy(f):
        return numpy.array(f)
except Exception as e:
    print(f"WARINING! Numba failed to import! Score calculation will lag!")
    def wrap_numpy(f):
        return f
    from builtins import range as prange
    def njit(parallel=False):
        def Inner(func): return lambda *args, **kwargs: func(*args, **kwargs)
        return Inner


@njit
def _accurate_scoring_core(f, o, b, heuristic):
    scores = [0, 0, 0]

    # Brute force implementation that turned out to be incredibly slow
    # Possible optimizations: convert to 1D array
    D_Is = [0, -1, -1, -1, 0, +1, +1, +1]
    D_Us = [+1, +1, 0, -1, -1, -1, 0, +1]
    for color in range(3):
        #processed_states = set()
        #processed_states.add(0)
        for start_i in range(1, len(f) - 1):
            for start_u in range(1, len(f[0]) - 1):
                if color != f[start_i][start_u]:
                    continue
                if heuristic:
                    neighbors = sum([f[start_i + D_Is[y]][start_u + D_Us[y]] == color for y in range(8)])
                    if neighbors > 5:
                        break
                pos_i, pos_u = start_i, start_u
                st = [-1]
                #st_bitset = 0
                while len(st):
                    scores[color] = max(scores[color], len(st))
                    bite_head = True
                    o[pos_i][pos_u] = True
                    #st_bitset ^= 1 << b[pos_i][pos_u]

                    if True:
                    #if st_bitset | (b[pos_i][pos_u] << 42) not in processed_states:
                    #    processed_states.add(st_bitset | (b[pos_i][pos_u] << 42))
                        for dir in range(st[-1] + 1, 8):
                            d_i: int = D_Is[dir]
                            d_u: int = D_Us[dir]
                            if f[pos_i + d_i][pos_u + d_u] == color and not o[pos_i + d_i][pos_u + d_u]:
                                st[-1] = dir
                                st.append(-1)
                                pos_i += d_i
                                pos_u += d_u
                                bite_head = False
                                break
                    if bite_head:
                        st.pop()
                        o[pos_i][pos_u] = False
                        #st_bitset ^= 1 << b[pos_i][pos_u]
                        if len(st) == 0:
                            break
                        pos_i -= D_Is[st[-1]]
                        pos_u -= D_Us[st[-1]]
    return scores


def score(f, accurate=False, heuristic=False):
    f = ['b' * len(f[0])] + f + ['r' * len(f[0])]
    f = ['b' + x + 'b' for x in f]
    def conv(el):
        if el == 'B': return 0
        if el == 'G': return 1
        if el == 'Y': return 2
        return -1
    f = [[conv(el) for el in row] for row in f]
    f = wrap_numpy(f)

    if accurate:
        o = [[False] * len(x) for x in f]
        o = wrap_numpy(o)

        b_c = [0, 0, 0, 0]
        b = [[0 for _ in range(len(x))] for x in f]
        for i in range(len(b)):
            for u in range(len(b[i])):
                b[i][u] = b_c[f[i][u]]
                b_c[f[i][u]] += 1
        b = wrap_numpy(b)

        sc = _accurate_scoring_core(f, o, b, heuristic)
    else:
        sc = approximate_score(f)
    scores = {'B': sc[0], 'G': sc[1], 'Y': sc[2], 'total': sum(sc)}
    return scores

@njit
def approximate_score(f, iters=20_000):
    """Calculates score using Monte-carlo. In each iteration, a random cell is used.
    Then, extend operation is used as many times as possible, each time incrementing the snake length by one.
    Each time, incrementing is attempted for a random cell. Extending can be done in four ways:
    first cell, extend "tail", extend "head", or extend in the middle."""
    f_ii = len(f) - 2
    f_uu = len(f[0]) - 2

    scores = [0, 0, 0]

    # Quick pseudorandom number generator
    random_state = 777
    def new_coords():
        nonlocal random_state

        random_state = (28 * random_state + 13) % 1_000_033
        q_i = 1 + (random_state >> 8) % f_ii
        q_u = 1 + random_state % f_uu
        return q_i, q_u

    def is_neighbor(i1, u1, i2, u2):
        return abs(i1 - i2) <= 1 and abs(u1 - u2) <= 1

    snaek = []
    queued = [[False] * len(x) for x in f]
    done = [[False] * len(x) for x in f]
    for current_iter in range(iters):
        i, u = 1 + (current_iter % f_ii), 1 + ((current_iter // f_ii) % f_uu)
        color = f[i][u]
        if color < 0:
            continue

        queued[i][u] = True
        qq = 1
        while qq:
            while not queued[i][u]:
                i, u = new_coords()
            approved = False
            idx = -1
            if len(snaek):
                if is_neighbor(snaek[0][0], snaek[0][1], i, u):
                    idx = 0
                    approved = True
                elif is_neighbor(snaek[-1][0], snaek[-1][1], i, u):
                    idx = len(snaek) - 1
                    approved = True
            else:
                approved = True
                idx = 0
            if not approved:
                for snaek_ik in range(0, 103 * (len(snaek) - 1), 103):
                    snaek_i = snaek_ik % (len(snaek) - 1)
                    if is_neighbor(snaek[snaek_i][0], snaek[snaek_i][1], i, u) \
                            and is_neighbor(snaek[snaek_i + 1][0], snaek[snaek_i + 1][1], i, u):
                        approved = True
                        idx = snaek_i + 1

            if not approved:
                queued[i][u] = False
                qq -= 1
                continue

            snaek.insert(idx, (i, u))
            for ni in range(i-1, i+2):
                for nu in range(u-1, u+2):
                    if f[ni][nu] == color and not done[ni][nu] and not queued[ni][nu]:
                        queued[ni][nu] = True
                        qq += 1
            done[i][u] = True
            queued[i][u] = False
            qq -= 1
        scores[color] = max(scores[color], len(snaek))
        for i, u in snaek:
            done[i][u] = False
        snaek.clear()
    return scores
