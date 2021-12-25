class TechnionFCPlayer:
    """This object represents a Technion FC player"""
    def __init__(self, user, liable=False, approved=False, match_ball=False):
        self.user = user                    # telegram User object
        self.liable = liable                # match liability
        self.approved = approved            # indicates whether the player has approved he'll be attending
        self.match_ball = match_ball        # indicates whether the player will bring a match ball

    def __eq__(self, other):
        if isinstance(other, TechnionFCPlayer):
            return self.user.id == other.user.id
        return False
