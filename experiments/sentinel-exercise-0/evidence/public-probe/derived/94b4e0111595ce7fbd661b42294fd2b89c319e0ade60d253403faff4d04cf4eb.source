"""Trusted direct tests of pinned public code generation; never run generated code."""
import ast
import shlex
import unittest
from operator_recipe import cell as native_cell


class RecipeTests(unittest.TestCase):
    def test_argv_roundtrip(self):
        python='/approved python/bin/python'
        onecall='/approved tool/onecall.py'
        root='/approved source'
        query='a "quote"; $(synthetic-command) `literal`\nnext line'
        out='/approved derived'
        tree=ast.parse(native_cell(python,onecall,root,query,out))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='terminal')
        self.assertEqual(shlex.split(ast.literal_eval(call.args[0])),
                         [python,onecall,'evidence','--root',root,'--query',query,'--out',out])
        self.assertEqual(ast.literal_eval(call.keywords[0].value),40)

    def test_one_terminal_call(self):
        tree=ast.parse(native_cell('python','onecall.py','root','needle','derived'))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='terminal']
        self.assertEqual(len(calls),1)
        imports=[n for n in tree.body if isinstance(n,ast.ImportFrom)]
        self.assertEqual(imports[0].module,'hermes_tools')

    def test_green_decoy(self):
        self.assertEqual(2+2,4)
