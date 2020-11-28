from abc import abstractmethod


class ProcessMatch(object):
    @abstractmethod
    def may_match(self):
        pass

    def get_pid(self):
        try:
            return self.pid
        except:
            return self.process.pid
    
    def get_custom_display_name(self):
        try:
            return self.name + ' - ' + self.process_type
        except:
            return self.process.process_type

    def get_match_score(self, other):
        score = 0
        for attr in self.__dict__.keys():
            if self.__dict__[attr] == other.__dict__[attr]:
                score += 1
        return score

    def get_process_name(self):
        try:
            return self.name
        except:
            return self.process.name

    def get_process_arguments(self):
        try:
            return self.args
        except:
            return self.process.args
