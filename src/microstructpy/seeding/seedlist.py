"""Seed List

This module contains the class definition for the SeedList class.
"""
# --------------------------------------------------------------------------- #
#                                                                             #
# Import Modules                                                              #
#                                                                             #
# --------------------------------------------------------------------------- #

from __future__ import division
from __future__ import print_function

import warnings

import aabbtree
import numpy as np
import scipy.stats
from matplotlib import collections
from matplotlib import patches
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
from mpl_toolkits.mplot3d import Axes3D
from pyquaternion import Quaternion
from scipy.spatial import distance

from microstructpy import _misc
from microstructpy import geometry
from microstructpy.seeding import seed as _seed

__all__ = ['SeedList']
__author__ = 'Kenneth (Kip) Hart'


# --------------------------------------------------------------------------- #
#                                                                             #
# SeedList Class                                                              #
#                                                                             #
# --------------------------------------------------------------------------- #
class SeedList:
    """List of seed geometries.

    The SeedList is similar to a standard Python list, but contains instances
    of the :class:`.Seed` class. It can be generated from a list of Seeds,
    by creating enough seeds to fill a given volume, or by reading the content
    of a cache text file.

    Args:
        seeds (list): *(optional)* List of :class:`.Seed` instances. Default
            is None, which is creates an empty list.

    """
    # ----------------------------------------------------------------------- #
    # Constructors                                                            #
    # ----------------------------------------------------------------------- #
    def __init__(self, seeds=None):
        if seeds is None:
            self.seeds = []
        else:
            self.seeds = seeds

    @classmethod
    def from_file(cls, filename):
        """Create seed list from file containing list of seeds

        This function creates a seed list from a file containing a list of
        seeds. This file should contain the string representations of seeds,
        separated by a newline character (which is the behavior of
        :meth:`write`).

        Args:
            filename (str): File containing the seed list.

        Returns:
            SeedList: Instance of class.
        """
        with open(filename, 'r') as file:
            file_str = file.read()

        beg = 'Geometry:'
        rem = file_str.split(beg)[1:]

        return cls([_seed.Seed.from_str(beg + s) for s in rem])

    @classmethod
    def from_info(cls, phases, volume, rng_seeds=None):
        """Create seed list from microstructure information

        This function creates a seed list from information about the
        microstruture. The "phases" input should be a list of material
        phase dictionaries, formatted according to the :ref:`phase_dict_guide`
        guide.

        The "volume" input is the minimum volume of the list of seeds. Seeds
        will be added to the list until this volume threshold is crossed.

        Finally, the "rng_seeds" input is a dictionary of random number
        generator (RNG) seeds for each parameter of the seed geometries.
        For example, if one of the phases uses "size" to define the seeds,
        then "size" could be a keyword of the "rng_seeds" input. The value
        should be a non-negative integer, to seed the RNG for size.
        The default RNG seed is 0.

        Note:
            If two or more parameters have the same RNG seed and the same
            kernel of the distribution, those parameters will **not** be
            correlated. This method updates RNG seeds based on the order that
            distributions are sampled to avoid correlation between independent
            random variables.

        Args:
            phases (dict): Dictionary of phase information, see
                :ref:`phase_dict_guide` for a guide.
            volume (float): The total area/volume of the seeds in the list.
            rng_seeds (dict): *(optional)* Dictionary of RNG seeds for each
                step in the seeding process. The dictionary keys should match
                shape parameters in ``phases``. For example::

                    rng_seeds = {
                        'size': 0,
                        'angle': 3,
                    }

                Default is None, which initializes all RNG seeds to 0.

        Returns:
            SeedList: An instance of the class containing seeds prescribed by
            the phase information and filling the given volume.

        """
        if rng_seeds is None:
            rng_seeds = {}

        if isinstance(phases, dict):
            phases = [phases]

        # Set RNG Seeds
        max_int = np.iinfo(np.int32).max
        sample_rng_seeds = _set_sample_rng_seeds(phases, rng_seeds, max_int)

        # determine dimensionality, set default shape
        n_dim = _get_n_dim(phases)
        for phase in phases:
            if 'shape' in phase:
                assert geometry.factory(phase['shape']).n_dim == n_dim
            else:
                phase['shape'] = {2: 'circle', 3: 'sphere'}[n_dim]

        # compute population fractions for each phase
        pop_fracs = _calc_pop_fracs(n_dim, phases, sample_rng_seeds, max_int)
        p_dist = scipy.stats.rv_histogram((pop_fracs,
                                           np.arange(len(phases) + 1)))

        seed_vol = 0
        seeds = []
        while seed_vol < volume:
            # Pick the phase
            rng_seed = sample_rng_seeds['phase']
            phase_num = int(p_dist.rvs(random_state=rng_seed))
            sample_rng_seeds['phase'] = (rng_seed + 1) % max_int

            # Create the seed
            s_kwargs = _sample_phase_args(phases[phase_num], sample_rng_seeds,
                                          n_dim, max_int)
            s_kwargs['phase'] = phase_num

            # Add seed to list
            seeds.append(_seed.Seed.factory(phases[phase_num]['shape'],
                                            **s_kwargs))
            seed_vol += seeds[-1].volume

        return cls(seeds)

    # ----------------------------------------------------------------------- #
    # Representation and String Functions                                     #
    # ----------------------------------------------------------------------- #
    def __repr__(self):
        repr_str = 'SeedList('
        repr_str += repr(self.seeds)
        repr_str += ')'
        return repr_str

    def __str__(self):
        str_str = '\n'.join([str(s) for s in self.seeds])
        return str_str

    # ----------------------------------------------------------------------- #
    # List Methods                                                            #
    # ----------------------------------------------------------------------- #
    def __getitem__(self, i):
        if isinstance(i, slice):
            return SeedList(self.seeds[i])

        try:
            return self.seeds[i]
        except TypeError:
            indices = np.arange(len(self))[i]
            return SeedList([self.seeds[ind] for ind in indices])

    def __setitem__(self, i, s):
        try:
            self.seeds[int(i)] = s
        except TypeError:
            n_added = 0
            for ind, i_val in enumerate(i):
                if str(i_val) == 'True':
                    self.seeds[ind] = s[n_added]
                    n_added += 1
                elif str(i_val) != 'False':
                    self.seeds[int(i_val)] = s[ind]

    def __add__(self, seedlist):
        """Add seed lists together

        This function overloads the + operator, similar to
        :meth:`list.__add__`.

        Args:
            seedlist (SeedList, list): List of seeds to add.

        Returns:
            SeedList: Instance that joins the two seed lists.

        .. versionadded:: 1.1
        """
        if isinstance(seedlist, SeedList):
            return SeedList(self.seeds + seedlist.seeds)
        return SeedList(self.seeds + seedlist)

    def __len__(self):
        return len(self.seeds)

    def append(self, seed):
        """Append seed

        This function appends a seed to the list.

        Args:
            seed (Seed): The seed to append to the list

        """
        self.seeds.append(seed)

    def extend(self, seeds):
        """Extend seed list

        This function adds a list of seeds to the end of the seed list.

        Args:
            seeds (list or SeedList): List of seeds

        """
        if isinstance(seeds, SeedList):
            self.seeds.extend(seeds.seeds)
        else:
            self.seeds.extend(seeds)

    # ----------------------------------------------------------------------- #
    # Comparison Methods                                                      #
    # ----------------------------------------------------------------------- #
    def __eq__(self, other_list):
        same = len(self) == len(other_list)
        if same:
            for s1, s2 in zip(self, other_list):
                same &= s1 == s2
        return same

    # ----------------------------------------------------------------------- #
    # Write Function                                                          #
    # ----------------------------------------------------------------------- #
    def write(self, filename, format='txt'):
        """Write seed list to a text file

        This function writes out the seed list to a file. The format of the
        file can be either 'txt' or 'vtk'. The content of the 'txt' file
        is human-readable and can be read by the
        :func:`SeedList.from_file` method.
        The 'vtk' option creates a VTK legacy file with the grain geometries.

        For grains that are non-spherical, the spherical breakdown of the seed
        is output instead of the seed itself.

        Args:
            filename (str): File to write the seed list.
        """

        if format == 'txt':
            with open(filename, 'w') as file:
                file.write(str(self) + '\n')
        elif format == 'vtk':
            # Unpack breakdowns
            bkdwns = np.array([b for s in self for b in s.breakdown])
            n_pts, n_col = bkdwns.shape  # pylint: disable=E0633
            # E0633: unpacking-non-sequence
            seed_nums = np.array([i for i, s in enumerate(self) for b in
                                  s.breakdown])
            centers = np.zeros((n_pts, 3))
            centers[:, :(n_col - 1)] = bkdwns[:, :-1]
            diameters = 2 * bkdwns[:, -1]

            pt_fmt = '{: f} {: f} {: f}\n'
            # write heading
            vtk = '# vtk DataFile Version 2.0\n'
            vtk += 'Tetrahedral mesh\n'
            vtk += 'ASCII\n'
            vtk += 'DATASET POLYDATA\n'

            # Write points
            vtk += 'POINTS ' + str(n_pts) + ' float\n'
            vtk += ''.join([pt_fmt.format(*c) for c in centers])

            # Write diameters
            vtk += '\nPOINT_DATA ' + str(n_pts) + '\n'
            vtk += 'SCALARS diameters double 1 \n'
            vtk += 'LOOKUP_TABLE Diameters\n'
            vtk += ''.join([str(d) + '\n' for d in diameters])

            # Write material numbers
            vtk += '\nSCALARS phase_numbers int 1 \n'
            vtk += 'LOOKUP_TABLE phase_numbers\n'
            vtk += ''.join([str(self[n].phase) + '\n' for n in seed_nums])

            # Write seed numbers
            vtk += '\nSCALARS seed_numbers int 1 \n'
            vtk += 'LOOKUP_TABLE seed_numbers \n'
            vtk += ''.join([str(n) + '\n' for n in seed_nums])

            with open(filename, 'w') as file:
                file.write(vtk)

        else:
            raise ValueError('Cannot write to format ' + str(format))

    # ----------------------------------------------------------------------- #
    # Plot Function                                                           #
    # ----------------------------------------------------------------------- #
    def plot(self, index_by='seed', material=None, loc=0, **kwargs):
        """Plot the seeds in the seed list.

        This function plots the seeds contained in the seed list.
        In 2D, the seeds are grouped into matplotlib collections to reduce
        the computational load. In 3D, matplotlib does not have patches, so
        each seed is rendered as its own surface.

        Additional keyword arguments can be specified and passed through to
        matplotlib. These arguments should be either single values
        (e.g. ``edgecolors='k'``), or lists of values that have the same
        length as the seed list.

        Args:
            index_by (str): *(optional)* {'material' | 'seed'}
                Flag for indexing into the other arrays passed into the
                function. For example,
                ``plot(index_by='material', color=['blue', 'red'])`` will plot
                the seeds with ``phase`` equal to 0 in blue, and seeds with
                ``phase`` equal to 1 in red. Defaults to 'seed'.
            material (list): *(optional)* Names of material phases. One entry
                per material phase (the ``index_by`` argument is ignored).
                If this argument is set, a legend is added to the plot with
                one entry per material.
            loc (int or str): *(optional)* The location of the legend,
                if 'material' is specified. This argument is passed directly
                through to :func:`matplotlib.pyplot.legend`. Defaults to 0,
                which is 'best' in matplotlib.
            **kwargs: Keyword arguments to pass to matplotlib

        """
        if material is None:
            material = []
        seed_args = _plt_args(self, index_by, kwargs)

        n = self.__getitem__(0).geometry.n_dim
        ax, lims = _get_axes(n)

        if n == 3:
            for seed, args in zip(self, seed_args):
                seed.plot(**args)

        elif n == 2:
            _plot_2d(ax, self, seed_args)

        # Add legend
        _add_legend(ax, material, self, seed_args, kwargs, index_by, loc)

        # Adjust Axes
        seed_lims = [np.array(s.geometry.limits).flatten() for s in self]
        mins = np.array(seed_lims)[:, 0::2].min(axis=0)
        maxs = np.array(seed_lims)[:, 1::2].max(axis=0)
        s_lims = list(zip(mins, maxs))
        lims = [(min(l1[0], l2[0]), max(l1[1], l2[1])) for l1, l2 in
                zip(lims, s_lims)]
        _misc.adjust_axes(ax, lims)

    def plot_breakdown(self, index_by='seed', material=None, loc=0, **kwargs):
        """Plot the breakdowns of the seeds in seed list.

        This function plots the breakdowns of seeds contained in the seed list.
        In 2D, the breakdowns are grouped into matplotlib collections to reduce
        the computational load. In 3D, matplotlib does not have patches, so
        each breakdown is rendered as its own surface.

        Additional keyword arguments can be specified and passed through to
        matplotlib. These arguments should be either single values
        (e.g. ``edgecolors='k'``), or lists of values that have the same
        length as the seed list.

        Args:
            index_by (str): *(optional)* {'material' | 'seed'}
                Flag for indexing into the other arrays passed into the
                function. For example,
                ``plot(index_by='material', color=['blue', 'red'])`` will plot
                the seeds with ``phase`` equal to 0 in blue, and seeds with
                ``phase`` equal to 1 in red. Defaults to 'seed'.
            material (list): *(optional)* Names of material phases. One entry
                per material phase (the ``index_by`` argument is ignored).
                If this argument is set, a legend is added to the plot with
                one entry per material.
            loc (int or str): *(optional)* The location of the legend,
                if 'material' is specified. This argument is passed directly
                through to :func:`matplotlib.pyplot.legend`. Defaults to 0,
                which is 'best' in matplotlib.
            **kwargs: Keyword arguments to pass to matplotlib

        """
        if material is None:
            material = []
        seed_args = _plt_args(self, index_by, kwargs)

        n = self.__getitem__(0).geometry.n_dim
        ax, lims = _get_axes(n)

        if n == 3:
            for seed, args in zip(self, seed_args):
                seed.plot_breakdown(**args)

        elif n == 2:
            _plot_2d_breakdowns(ax, self, seed_args)

        # Add legend
        _add_legend(ax, material, self, seed_args, kwargs, index_by, loc)

        # Adjust Axes
        seed_lims = [np.array(s.geometry.limits).flatten() for s in self]
        mins = np.array(seed_lims)[:, 0::2].min(axis=0)
        maxs = np.array(seed_lims)[:, 1::2].max(axis=0)
        s_lims = list(zip(mins, maxs))
        lims = [(min(l1[0], l2[0]), max(l1[1], l2[1])) for l1, l2 in
                zip(lims, s_lims)]
        _misc.adjust_axes(ax, lims)

    # ----------------------------------------------------------------------- #
    # Position Function                                                       #
    # ----------------------------------------------------------------------- #
    def position(self, domain, pos_dists=None, rng_seed=0, hold=None,
                 **kwargs):
        """Position seeds in a domain

        This method positions the seeds within a domain. The "domain" should be
        a geometry instance from the :mod:`microstructpy.geometry` module.

        The "pos_dist" input is for phases with custom position distributions,
        the default being a uniform random distribution.
        For example:

        .. code-block:: python

            import scipy.stats
            mu = [0.5, -0.2]
            sigma = [[2.0, 0.3], [0.3, 0.5]]
            pos_dists = {2: scipy.stats.multivariate_normal(mu, sigma),
                         3: ['random',
                             scipy.stats.norm(0, 1)]
                         }

        Here, phases 0 and 1 have the default distribution, phase 2 has a
        bivariate normal position distribution, and phase 3 is uniform in the
        x and normally distributed in the y. Multivariate distributions are
        described in the multivariate section of the :mod:`scipy.stats`
        documentation.

        The position of certain seeds can be held fixed during the positioning
        process using the "hold" input. This should be a list of booleans,
        where False indicates a seed should not be held fixed and True
        indicates that it should be held fixed. The default behavior is to not
        hold any seeds fixed.

        The "rtol" parameter governs the relative overlap tolerable between
        seeds. Setting rtol to 0 means that there is no overlap, while a value
        of 1 means that one seed's center is on the edge of another seed.
        The default value is 'fit', which determines a tolerance between 0 and
        1 based on the ratio of standard deviation to mean in grain volumes.

        Args:
            domain (from :mod:`microstructpy.geometry`): The domain of the
                microstructure.
            pos_dists (dict): *(optional)* Position distributions for each
                phase, formatted like the example above.
                Defaults to uniform random throughout the domain.
            rng_seed (int): *(optional)* Random number generator (RNG) seed
                for positioning the seeds. Should be a non-negative integer.
            hold (list or numpy.ndarray): *(optional)* List of booleans for
                holding the positions of seeds.
                Defaults to False for all seeds.
            max_attempts (int): *(optional)* Number of random trials before
                removing a seed from the list.
                Defaults to 10,000.
            rtol (str or float): *(optional)* The relative overlap tolerance
                between seeds. This parameter should be between 0 and 1.
                Using the 'fit' option, a function will determine the value
                for rtol based on the mean and standard deviation in seed
                volumes. Defaults to 'fit'.
            verbose (bool): *(optional)* This option will print a running
                counter of how many seeds have been positioned.
                Defaults to False.

        """  # NOQA: E501
        max_attempts = kwargs.get('max_attempts', 10000)
        verbose = kwargs.get('verbose', False)
        if hold is None:
            hold = [False for seed in self]

        # set the spatial distributions
        u_dist = [scipy.stats.uniform(lb, ub - lb) for lb, ub in
                  domain.sample_limits]

        distribs = []
        n_phases = max([s.phase for s in self]) + 1
        for i in range(n_phases):
            try:
                distribs.append(pos_dists.get(i, u_dist))
            except AttributeError:
                distribs.append(u_dist)

        # Add hold seeds
        n_seeds = len(self)
        tree = aabbtree.AABBTree()
        for i in range(n_seeds):
            if hold[i]:
                # add to tree
                aabb = aabbtree.AABB(self[i].geometry.limits)
                tree.add(aabb, i)

        positioned = np.array(hold)
        i_sort = np.flip(np.argsort([s.volume for s in self]))
        i_position = i_sort[~positioned[i_sort]]

        # allowable overlap, relative to radius
        if kwargs.get('rtol', 'fit') == 'fit':
            rtol = calc_rtol(self)
        else:
            rtol = kwargs['rtol']

        # position the remaining seeds
        i_reject = []
        np.random.seed(rng_seed)
        n_samples = 100

        for k, i in enumerate(i_position):
            if verbose:
                print(k + 1, 'of', len(i_position))

            seed = self[i]
            pos_dist = distribs[seed.phase]

            searching = True
            n_attempts = 0
            i_sample = 0
            pts = _sample_pos_within(pos_dist, n_samples, domain)
            while searching and n_attempts < max_attempts:
                pt = pts[i_sample]
                seed.position = pt

                n_attempts += 1
                i_sample += 1
                if i_sample == n_samples:
                    pts = _sample_pos_within(pos_dist, n_samples, domain)
                    i_sample = 0

                searching = _seed_overlaps(seed, self, tree, rtol)

            if searching:
                i_reject.append(i)
            else:
                positioned[i] = True
                self[i] = seed

                # add to tree
                aabb = aabbtree.AABB(seed.geometry.limits)
                tree.add(aabb, i)

        keep_mask = np.array(n_seeds * [True])
        keep_mask[i_reject] = False

        if ~np.all(keep_mask):
            reject_seeds = self[~keep_mask]
            f = 'seed_position_reject.log'
            reject_seeds.write(f)

            w_str = 'Seeds were removed from the seed list during positioning.'
            w_str += ' Their data has beeen written to ' + f + ' and their'
            w_str += ' indices were ' + str(i_reject) + '.'
            warnings.warn(w_str, RuntimeWarning)

        self.seeds = self[keep_mask].seeds


def _get_n_dim(phases):
    n_dim = None
    for phase in phases:
        if 'shape' in phase:
            n_dim = geometry.factory(phase['shape']).n_dim
    if n_dim is None:
        e_str = 'Number of dimensions could not be determined from phase '
        e_str += 'shapes. Consider setting the shape of a phase, or'
        e_str += ' specifying the number of dimensions.'
        raise ValueError(e_str)
    return n_dim


def _set_sample_rng_seeds(phases, rng_seeds, maxint):
    rng_keys = list({k for p in phases for k in p} - set(_misc.gen_kws))
    rng_keys.extend(['fraction', 'phase'])

    n_keys = len(rng_keys)
    int_step = maxint / n_keys
    sample_seeds = {}
    for i, k in enumerate(rng_keys):
        rng_seed = int(rng_seeds.get(k, 0) + i * int_step)
        sample_seeds[k] = rng_seed % maxint
    return sample_seeds


def _calc_pop_fracs(n_dim, phases, sample_rng_seeds, max_int):
    # compute volume of each phase
    vol_rng = sample_rng_seeds['fraction']
    n_phases = len(phases)
    rel_vols = np.ones(n_phases)
    for i, phase in enumerate(phases):
        vol = phase.get('fraction', 1)
        try:
            v_sample = -1
            while v_sample < 0:
                v_sample = vol.rvs(random_state=vol_rng)
                vol_rng = (vol_rng + 1) % max_int
            rel_vols[i] = v_sample
        except AttributeError:
            rel_vols[i] = vol
    vol_fracs = rel_vols / sum(rel_vols)

    # Compute the average grain volume of each phase
    if n_dim == 2:
        avg_vols = [geometry.factory(p['shape']).area_expectation(**p)
                    for p in phases]
    else:
        avg_vols = [geometry.factory(p['shape']).volume_expectation(**p)
                    for p in phases]
    weights = vol_fracs / np.array(avg_vols)
    pop_fracs = weights / sum(weights)
    return pop_fracs


def _sample_phase_args(phase, sample_rng_seeds, n_dim, maxint):
    seed_kwargs = {}
    for kw in set(phase) - set(_misc.gen_kws):
        rng_seed = sample_rng_seeds[kw]

        # Sample, with special cases for orientation
        if kw not in _misc.ori_kws:
            try:
                val = phase[kw].rvs(random_state=rng_seed)
            except AttributeError:
                val = phase[kw]
            seed_kwargs[kw] = val
        elif (phase[kw] == 'random') and (n_dim == 2):
            np.random.seed(rng_seed)
            ang_dist = scipy.stats.uniform(loc=0, scale=360)
            seed_kwargs['angle_deg'] = ang_dist.rvs(random_state=rng_seed)
        elif phase[kw] == 'random':
            quat_dist = scipy.stats.norm()
            elems = quat_dist.rvs(4, random_state=rng_seed)
            mag = np.linalg.norm(elems)
            elems /= mag
            val = Quaternion(elems).rotation_matrix
            seed_kwargs[kw] = val
        elif kw in ['rot_seq', 'rot_seq_deg', 'rot_seq_rad']:
            seq = []
            val = phase[kw]
            if not isinstance(val, list):
                val = [val]
            for rot_i, rotation in enumerate(val):
                rot_dict = {str(kw): rotation[kw] for kw in rotation}
                ax = rot_dict.get('axis', 'x')
                ang_dist = rot_dict.get('angle', 0)
                rot_rng = (rng_seed + rot_i) % maxint
                try:
                    ang = ang_dist.rvs(random_state=rot_rng)
                except AttributeError:
                    ang = ang_dist
                seq.append((ax, ang))
            seed_kwargs[kw] = seq
        else:
            try:
                val = phase[kw].rvs(random_state=rng_seed)
            except AttributeError:
                val = phase[kw]
            seed_kwargs[kw] = val

        # Update the RNG seed
        sample_rng_seeds[kw] = (rng_seed + 1) % maxint
    return seed_kwargs


def _plt_args(seeds, index_by, kwargs):
    seed_args = [{} for seed in seeds]
    for seed_num, seed in enumerate(seeds):
        phase_num = seed.phase
        for key, val in kwargs.items():
            if type(val) in (list, np.array):
                if index_by == 'seed' and len(val) > seed_num:
                    seed_args[seed_num][key] = val[seed_num]
                elif index_by == 'material' and len(val) > phase_num:
                    seed_args[seed_num][key] = val[phase_num]
            else:
                seed_args[seed_num][key] = val
    return seed_args


def _get_axes(n):
    if n == 2:
        ax = plt.gca()
    else:
        ax = plt.gcf().gca(projection=Axes3D.name)
    n_obj = _misc.ax_objects(ax)
    if n_obj > 0:
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
    else:
        xlim = [float('inf'), -float('inf')]
        ylim = [float('inf'), -float('inf')]

    lims = [xlim, ylim]

    if n == 3:
        if n_obj > 0:
            zlim = ax.get_zlim()
        else:
            zlim = [float('inf'), -float('inf')]
        lims.append(zlim)
    return ax, lims


def _plot_2d(ax, seeds, seed_args):
    ellipse_data = {'w': [], 'h': [], 'a': [], 'xy': []}
    ec_kwargs = {}

    rect_data = []
    rect_kwargs = {}
    for seed, args in zip(seeds, seed_args):
        geom_name = type(seed.geometry).__name__.lower().strip()
        if geom_name == 'ellipse':
            ellipse_data['w'].append(2 * seed.geometry.a)
            ellipse_data['h'].append(2 * seed.geometry.b)
            ellipse_data['a'].append(seed.geometry.angle_deg)
            ellipse_data['xy'].append(np.array(seed.position))

            for key, val in args.items():
                val_list = ec_kwargs.get(key, []) + [val]
                ec_kwargs[key] = val_list

        elif geom_name == 'circle':
            ellipse_data['w'].append(seed.geometry.diameter)
            ellipse_data['h'].append(seed.geometry.diameter)
            ellipse_data['a'].append(0)
            ellipse_data['xy'].append(np.array(seed.position))

            for key, val in args.items():
                val_list = ec_kwargs.get(key, []) + [val]
                ec_kwargs[key] = val_list

        elif geom_name in ['rectangle', 'square']:
            w, h = seed.geometry.side_lengths
            corner = seed.geometry.corner
            t = seed.geometry.angle_deg
            rect_inputs = {'width': w, 'height': h, 'angle': t, 'xy': corner}
            rect_data.append(rect_inputs)

            for key, val in args.items():
                val_list = rect_kwargs.get(key, []) + [val]
                rect_kwargs[key] = val_list

        elif geom_name == 'nonetype':
            pass

        else:
            e_str = 'Cannot plot groups of ' + geom_name + ' yet.'
            raise NotImplementedError(e_str)

    # abbreviate kwargs if all the same
    for key, val in ec_kwargs.items():
        v1 = val[0]
        same = True
        for v in val:
            same &= v == v1
        if same:
            ec_kwargs[key] = v1

    # Plot Circles and Ellipses
    w = np.array(ellipse_data['w'])
    h = np.array(ellipse_data['h'])
    a = np.array(ellipse_data['a'])
    xy = np.array(ellipse_data['xy'])
    ec = collections.EllipseCollection(w, h, a, units='x', offsets=xy,
                                       transOffset=ax.transData, **ec_kwargs)
    ax.add_collection(ec)

    # Plot Rectangles
    rects = [Rectangle(**rect_inps) for rect_inps in rect_data]
    rc = collections.PatchCollection(rects, False, **rect_kwargs)
    ax.add_collection(rc)

    ax.autoscale_view()


def _plot_2d_breakdowns(ax, seeds, seed_args):
    breakdowns = np.zeros((0, 3))
    ec_kwargs = {}
    for seed, args in zip(seeds, seed_args):
        breakdowns = np.concatenate((breakdowns, seed.breakdown))
        n_c = len(seed.breakdown)
        for key, val in args.items():
            val_list = ec_kwargs.get(key, [])
            val_list.extend(n_c * [val])
            ec_kwargs[key] = val_list
    d = 2 * breakdowns[:, -1]
    xy = breakdowns[:, :-1]
    a = np.full(len(breakdowns), 0)

    # abbreviate kwargs if all the same
    for key, val in ec_kwargs.items():
        v1 = val[0]
        same = True
        for v in val:
            same &= v == v1
        if same:
            ec_kwargs[key] = v1

    ec = collections.EllipseCollection(d, d, a, units='x', offsets=xy,
                                       transOffset=ax.transData, **ec_kwargs)
    ax.add_collection(ec)
    ax.autoscale_view()


def _add_legend(ax, material, seeds, seed_args, kwargs, index_by, loc):
    if material:
        p_kwargs = [{'label': m} for m in material]
        if index_by == 'seed':
            for seed_kwargs, seed in zip(seed_args, seeds):
                p_kwargs[seed.phase].update(seed_kwargs)
        else:
            for key, val in kwargs.items():
                if type(val) in (list, np.array):
                    for i, elem in enumerate(val):
                        p_kwargs[i][key] = elem
                else:
                    for p_kwargs_i in p_kwargs:
                        p_kwargs_i[key] = val

        # Replace plural keywords
        for p_kw in p_kwargs:
            for kw in _misc.mpl_plural_kwargs:
                if kw in p_kw:
                    p_kw[kw[:-1]] = p_kw[kw]
                    del p_kw[kw]
        ax.legend(handles=[patches.Patch(**p_kw) for p_kw in p_kwargs],
                  loc=loc)


def calc_rtol(seeds):
    """Calculate relative overlap tolerance."""
    cv = scipy.stats.variation([s.volume for s in seeds])
    n_dim = seeds[0].geometry.n_dim
    if n_dim == 2:
        numer = 0.362954 * cv * cv - 0.419069 * cv + .184959
        denom = cv * cv - 1.05989 * cv + 0.365096
        rtol = numer / denom
    elif n_dim == 3:
        numer = 0.471115 * cv * cv - 0.602324 * cv + 0.297562
        denom = cv * cv - 1.08469 * cv + 0.428216
        rtol = numer / denom
    else:
        raise ValueError('Cannot calculate rtol for {}-D.'.format(n_dim))
    return rtol


def sample_pos(distribution, n=1):
    """ Sample position distribution

    This function returns a sample of the postion distribution.
    This distribution can be either a list of independent distributions
    for each axis, or a single multi-variate distribution. A list of
    multi-variate distributions is given on the `SciPy stats website`_.

    Two examples of position distributions are given below.

    .. code-block:: python

        # three independent distributions
        distribution = [scipy.stats.uniform(-1, 2),
                        scipy.stats.norm(0, 1),
                        scipy.stats.binom(5, 0.4)]

        # one multi-variate distribution
        mu = [2, -3 , 5]
        sigma = [[1, 3, 0], [3, 1, 2], [0, 2, 2]]
        distribution = scipy.stats.multivariate_normal(mu, sigma)

    Args:
        distribution (list or scipy.stats distribution): The position
            distribution.

        n (int): *(optional)* Number of samples. Defaults to 1.

    Returns:
        list: A sample of the distribution.
    """  # NOQA : E501
    try:
        pos = distribution.rvs(n)
    except AttributeError:
        pos = np.full((n, len(distribution)), 0, dtype='float')
        for j, coord_dist in enumerate(distribution):
            try:
                pos[:, j] = coord_dist.rvs(n)
            except AttributeError:
                pos[:, j] = coord_dist

    if n == 1:
        return pos[0]
    return pos


def _sample_pos_within(distribution, n, domain):
    pos = []
    while len(pos) < n:
        samples = sample_pos(distribution, n)
        mask = domain.within(samples)
        pos.extend(samples[mask])
    if n == 1:
        return pos
    return np.array(pos[:n])


def _seed_overlaps(seed, seeds, tree, rtol):
    aabb = aabbtree.AABB(seed.geometry.limits)
    bkdwn = np.array(seed.breakdown)
    cens = bkdwn[:, :-1]
    rads = bkdwn[:, -1].reshape(-1, 1)

    for olap_seed in seeds[tree.overlap_values(aabb, method='BFS')]:
        o_bkdwn = np.array(olap_seed.breakdown)
        o_cens = o_bkdwn[:, :-1]
        o_rads = o_bkdwn[:, -1].reshape(1, -1)

        if len(rads) > 1:
            dists = distance.cdist(cens, o_cens)
        else:
            rel_pos = o_cens - cens
            dists = np.sqrt(np.sum(rel_pos * rel_pos, axis=1))
        if np.any(dists + rtol * np.minimum(rads, o_rads) < rads + o_rads):
            return True
    return False
