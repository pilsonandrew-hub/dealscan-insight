import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      "@typescript-eslint/no-unused-vars": "off",
      // Prevent incorrect default import usage for ProtectedRoute
      "no-restricted-imports": [
        "error",
        {
          "paths": [
            {
              "name": "@/components/ProtectedRoute",
              "importNames": ["ProtectedRoute"],
              "message": "Use default import for ProtectedRoute: import ProtectedRoute from '@/components/ProtectedRoute'"
            }
          ]
        }
      ],
      // Enforce consistent import/export patterns
      "import/no-default-export": "off",
      "@typescript-eslint/consistent-type-imports": [
        "error",
        {
          "prefer": "type-imports",
          "disallowTypeAnnotations": true
        }
      ]
    },
  }
);
