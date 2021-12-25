class TechnionFCPlayer:
    """This object represents a Technion FC player"""
    def __init__(self, user, liable=False):
        self.user = user            # telegram User object
        self.liable = liable        # match liability
