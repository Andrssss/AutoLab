from threading import Lock


# Ezekre végűl semmi szükség nincs, mert Global Interpreter úgyis csak 1 Proceszt enged egyszerre futtatni, DE 

# " As of Python 3.13, free-threaded builds can disable the GIL, enabling true parallel execution of threads, but this feature is not available by default "

# Ez egy elég új dolog, szóval mostmár meglehet oldani rendesen és a program bizonyos területein ezt ki is használom. 
# De ezekre a globális Lock -okra nincs szükség. Viszont törölni sok idő és mi van ha mégis jól jön.


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
