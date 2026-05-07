

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring physical telescope hardware"
    )
