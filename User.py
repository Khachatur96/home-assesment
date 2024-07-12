from dataclasses import dataclass

# @dataclass
class User:
    def __init__(self):
        pass  # Initialization logic, if needed

    def __str__(self):
        s = ""
        for key, value in self.__dict__.items():
            s += f"{key}: {value}\n"
