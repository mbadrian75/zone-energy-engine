"""Private, process-local replay seeds spilled to compressed temporary files.

These trusted pickle files are not user inputs or resumable checkpoints. Old
seeds retain references to earlier files rather than their in-memory graphs.
"""
import gzip
import os
from pathlib import Path
import pickle
from tempfile import TemporaryDirectory


class SeedReference:
    def __init__(self, archive, name):
        self.archive, self.name = archive, name

    def __copy__(self):
        return self.archive.load(self.name)


class _Pickler(pickle.Pickler):
    def __init__(self, file, archive):
        super().__init__(file, protocol=pickle.HIGHEST_PROTOCOL)
        self.archive = archive

    def persistent_id(self, obj):
        if obj is self.archive:
            return "archive"
        if obj is self.archive.service:
            return "boundary_service"
        return None


class _Unpickler(pickle.Unpickler):
    def __init__(self, file, archive):
        super().__init__(file)
        self.archive = archive

    def persistent_load(self, identity):
        if identity == "archive":
            return self.archive
        if identity == "boundary_service":
            return self.archive.service
        raise pickle.UnpicklingError("Unknown seed dependency")


class SeedArchive:
    def __init__(self, service):
        self.service = service
        self.directory = TemporaryDirectory(prefix="zone-energy-seeds-",
            dir=os.environ.get("ZONE_ENERGY_SEED_DIRECTORY") or None)
        self.count = self.bytes = self.loads = 0

    def store(self, seed):
        if isinstance(seed, SeedReference) or seed is None:
            return seed
        name = f"seed-{self.count + 1}.pkl.gz"
        path = Path(self.directory.name) / name
        with path.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1) as compressed:
                _Pickler(compressed, self).dump(seed)
        self.count += 1
        self.bytes += path.stat().st_size
        return SeedReference(self, name)

    def load(self, name):
        if Path(name).name != name:
            raise ValueError("Invalid seed identity")
        with gzip.open(Path(self.directory.name) / name, "rb") as source:
            seed = _Unpickler(source, self).load()
            # Read the footer to check gzip integrity, even for a small pickle.
            if source.read(1):
                raise ValueError("Unexpected trailing seed data")
        self.loads += 1
        return seed

    def close(self):
        self.directory.cleanup()

    def __del__(self):
        directory = getattr(self, "directory", None)
        if directory is not None:
            directory.cleanup()
