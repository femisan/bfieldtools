# -*- coding: utf-8 -*-
"""
Classes for magnetic sensors and sensor arrays
"""

import quadpy
import numpy as np
from abc import ABC, abstractmethod
from .line_conductor import LineConductor


class BaseSensor(ABC):
    def __init__(self):
        self.base_sensor = True
        super().__init__()

    def new_from_transform(self, transform):
        if self.base_sensor:
            d = self.__dict__.copy()
            d.pop("base_sensor")
            obj = self.__class__(**d)
            obj.finalize(transform)
            return obj
        else:
            raise TypeError("Sensor already finalized, to move use update_position")

    @abstractmethod
    def finalize(self, transform):
        self.base_sensor = False
        t = transform
        if not isinstance(t, np.ndarray):
            raise TypeError("transform must be ndarray")
        if not t.shape == (4, 4):
            raise ValueError("transform shape must be (4,4)")

    @abstractmethod
    def update_position(self, transform):
        t = transform
        if not isinstance(t, np.ndarray):
            raise TypeError("transform must be ndarray")
        if not t.shape == (4, 4):
            raise ValueError("transform shape must be (4,4)")

    @abstractmethod
    def measure_bfield(self):
        pass

    @abstractmethod
    def measure_afield(self):
        pass

    @abstractmethod
    def bfield_self(self, points):
        """
        Reciprocal B-field for the sensor

        Parameters
        ----------
        points : ndarray (N, 3)
            evaluation points

        Returns
        -------
        B-field at the evaluation points

        """
        pass

    @abstractmethod
    def afield_self(self, points):
        """
        Reciprocal vector potential for the sensor

        Parameters
        ----------
        points : ndarray (N, 3)
            evaluation points

        Returns
        -------
        B-field at the evaluation points

        """
        pass


class MagnetometerLoop(BaseSensor):
    def __init__(self, dimensions, quad_scheme="dunavant_01"):
        if len(dimensions) == 2:
            self.dimensions = tuple(dimensions)
        else:
            raise ValueError("len(dimensions) must be 2")
        self.quad_scheme = quad_scheme
        super().__init__()

    def init_geometry(self):
        r0 = self.dimensions[0] / 2
        r1 = self.dimensions[1] / 2
        points = np.zeros((4, 3))
        points[:, 0] = np.array([-r0, r0, r0, -r0])
        points[:, 1] = np.array([-r1, -r1, r1, r1])
        self.bounding_points = points

    def finalize(self, transform=np.eye(4)):
        t = transform
        super().finalize(t)

        self.init_geometry()

        self.quad_weights = self.scheme.weights
        self.area_points = np.zeros((len(self.scheme.points), 3))
        self.area_points[:, 0] = self.scheme.points[:, 0] * self.dimensions[0]
        self.area_points[:, 1] = self.scheme.points[:, 1] * self.dimensions[1]

        self.update_position(t)

    def update_position(self, transform=np.eye(4)):
        t = transform
        super().update_position(t)
        points = apply_transform(t, self.bounding_points)
        self.line_conductor = LineConductor([points])

        self.bfield_points = apply_transform(t, self.area_points)
        self.normal = t[:3, 2] / np.linalg.norm(t[:3, 2])

    @property
    def area(self):
        return np.prod(self.dimensions)

    @property
    def scheme(self):
        return quadpy.c2.__dict__[self.quad_scheme]()

    def measure_bfield(self, bfield_func):
        bfield = bfield_func(self.bfield_points)
        integral = np.einsum("ij,i,j->", bfield, self.quad_weights, self.normal)
        return integral

    def measure_afield(self, afield_func, scheme_degree=1):
        scheme = quadpy.c1.gauss_patterson(scheme_degree)
        lc = self.line_conductor
        segments = lc.discrete[0, 1:] - lc.discrete[0, :-1]
        # Points are from -1 to 1
        w = (scheme.points + 1) / 2
        quad_points = [
            p + w[:, None] * s for s, p in zip(segments, lc.discrete[0, :-1])
        ]
        # Nsegment, Nqpoints_per_segment, Nxyz
        quad_points = np.array(quad_points)
        shape = quad_points.shape
        afield = afield_func(quad_points.reshape(-1, 3)).reshape(shape)
        # scheme.weights sum to line length == 2
        weights = scheme.weights / 2

        # Sum integral using einsum
        return np.einsum("ijk,ik,j", afield, segments, weights)

    def bfield_self(self, points):
        return self.line_conductor.magnetic_field(points)

    def afield_self(self, points):
        return self.line_conductor.vector_potential(points)


class GradiometerLoop(BaseSensor):
    def __init__(self, dimensions, baseline, quad_scheme="dunavant_01"):
        self.dimensions = dimensions
        self.baseline = baseline
        self.quad_scheme = quad_scheme


class MagnetometerOPM(BaseSensor):
    def __init__(self, dimensions, scheme="hammer_stroud_1_3", Nq=None):
        pass

    @property
    def scheme(self):
        return quadpy.c3.__dict__[self.quad_scheme]()


class ThreeAxis(BaseSensor):
    def __init__(self, mag_points, mag_dirs=np.eye(3)):
        self.points = mag_points
        self.dirs = mag_dirs

    def finalize(self, transform):
        t = transform
        super().finalize(t)

    def update_position(self, transform):
        t = transform
        super().update_position(t)


def apply_transform(transform, points):
    """
    Parameters
    ----------
    transform : numpy array (4,4)
        4x4 transformation matrix for homogeneous coordinates
    points : numpy array (N, 3)
        points to be transformed

    Returns
    -------
    transformed points

    """
    return (transform[:3, :3] @ points.T + transform[:3, 3:]).T


class SensorArray:
    def __init__(self, base_sensor, transforms, names, Nq):
        self.transforms = transforms
        self.names = names
        self.sensors = {}

        for k, t in zip(self.names, self.transforms):
            sensor = base_sensor.new_from_transform(t)
            self.sensors[k] = sensor

    def fluxes(field_func):
        pass

    def bfields_self(self, points):
        return np.array([s.bfield_r(points) for s in self.sensors])

    def afields_self(self, points):
        return np.array([s.afield_r(points) for s in self.sensors])
