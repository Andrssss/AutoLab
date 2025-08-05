from threading import Lock

class LockRegistry:
    # Előre definiált lockok – ezek fixek, nem lehet bővíteni
    _locks = {
        "G-code_lock": Lock(),
        "Camera_lock": Lock(),
        "common": Lock()
    }

    @classmethod
    def get(cls, name):
        """Csak előre definiált neveket enged"""
        if name not in cls._locks:
            raise ValueError(f"Érvénytelen lock név: '{name}'")
        return cls._locks[name]

    @classmethod
    def keys(cls):
        return list(cls._locks.keys())

    @classmethod
    def all(cls):
        return cls._locks.copy()
