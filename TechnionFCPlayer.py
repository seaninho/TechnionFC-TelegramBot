class TechnionFCPlayer:
    """This object represents a Technion FC player"""
    def __init__(self, user, liable=False):
        self.user = user            # telegram User object
        self.liable = liable        # match liability

    def __eq__(self, other):
        if isinstance(other, TechnionFCPlayer):
            return self.user.id == other.user.id
        return False
