# -*- coding: utf-8 -*-


class NestedCollectorReprVisitor(object):
    def __init__(self):
        self.tree = ('ROOT', [])
        """ Each node is represented as a pair, the first element being
        the collector and the second a list of children collectors.
        This tree:
            ROOT - 1 - 1.2
              |    \-- 1.3
              |--- 2
              |--- 3 - 3.1 - 3.1.1
              |    \-- 3.2 - 3.2.1
              \--- 4
        Can be added with:
            x = PrettyCollectorTreeWriter();
            x(1, 0); x(1.1, 1); x(1.2, 1)
            x(2, 0)
            x(3, 0); x(3.1, 1); x(3.1.1, 2); x(3.2, 1); x(3.2.1, 2)
            x(4, 0)
        And results in:
            ('ROOT', [
              ('1', [
                ('1.1', []),
                ('1.2', [])] ),
              ('2', []),
              ('3', [
                ('3.1', [
                  ('3.1.1', [])]),
                ('3.2', [
                  ('3.2.1', [])])]),
              ('4', [])])
        """
        self.cur = [self.tree]
        self.depth = 0

    def __call__(self, collector, depth):
        assert(depth >= 0)
        assert(depth <= len(self.cur) - 1)
        while depth < len(self.cur) - 1:
            self.cur.pop()
        # append collector to the latest list of nodes
        self.cur[-1][1].append((str(collector), []))
        # our new current is the new tuple added
        self.cur.append(self.cur[-1][1][-1])


class TaskReprGenerator(object):
    PREFIX_LEAF_MID = "├── "
    PREFIX_LEAF_LAST = "└── "
    PREFIX_INNER_MID = "│   "
    PREFIX_INNER_LAST = "    "

    def __init__(self, task):
        self.task = task

    def __repr__(self):
        visitor = NestedCollectorReprVisitor()
        for collector in self.task.collectors:
            collector.apply_to_self(visitor)
        visitor.tree = (str(self.task.name) + "(" + str(self.task.task_id) + ")" " : " + str(self.task.description), visitor.tree[1])
        return TaskReprGenerator._stringify([visitor.tree])

    @staticmethod
    def _stringify(roots, prefix=''):
        res = ''
        for i, pair in enumerate(roots):
            is_last = (i==len(roots)-1)
            is_leaf = not pair[1]
            child_prefix = None
            if is_last:
                if is_leaf:
                    child_prefix = TaskReprGenerator.PREFIX_LEAF_LAST
                else:
                    child_prefix = TaskReprGenerator.PREFIX_INNER_LAST
            else:
                if is_leaf:
                    child_prefix = TaskReprGenerator.PREFIX_LEAF_MID
                else:
                    child_prefix = TaskReprGenerator.PREFIX_INNER_MID
            res += prefix + child_prefix + str(pair[0]) + "\n" + TaskReprGenerator._stringify(pair[1], prefix + child_prefix)
        return res
