from modules.llm import ask_llm


# ============================================================
# Generic Android Failure Report
# ============================================================

report = {
    "log": {
        "type": "ANR",
        "package": "com.example.demo",
        "process": "com.example.demo",
        "pid": 5479,
        "activity": "com.example.demo/.MainActivity",

        "exception": "",
        "reason": "Input dispatching timed out",
        "thread": "main",

        "stacktrace": "",

        "indicators": "input_dispatch_timeout",
        "confidence": "HIGH",
    },

    "source": {
        "file": "MainActivity.kt",

        "path": (
            "/home/vishal/AndroidStudioProjects/DEMO/"
            "app/src/main/java/com/example/demo/MainActivity.kt"
        ),

        "snippet": """
@Composable
fun ANRScreen(modifier: Modifier = Modifier) {

    Column(
        modifier = modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {

        Button(
            onClick = {
                Thread.sleep(60000)
            }
        ) {
            Text("Generate ANR")
        }
    }
}
""",

        "code": """
package com.example.demo

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.example.demo.ui.theme.DEMOTheme
import androidx.compose.foundation.layout.padding

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {

        super.onCreate(savedInstanceState)

        enableEdgeToEdge()

        setContent {

            DEMOTheme {

                Scaffold(
                    modifier = Modifier.fillMaxSize()
                ) { innerPadding ->

                    ANRScreen(
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }
}


@Composable
fun ANRScreen(modifier: Modifier = Modifier) {

    Column(
        modifier = modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {

        Button(
            onClick = {
                Thread.sleep(60000)
            }
        ) {
            Text("Generate ANR")
        }
    }
}
"""
    }
}


# ============================================================
# Call VAMP LLM
# ============================================================

print()
print("=" * 70)
print("                 VAMP LLM TEST")
print("=" * 70)

print()
print("Sending Android failure evidence to Gemini...")

patch = ask_llm(report)


# ============================================================
# Display Result
# ============================================================

print()
print("=" * 70)
print("                    LLM RESULT")
print("=" * 70)

print()
print("Root Cause:")
print(patch.root_cause)

print()
print("Confidence:")
print(patch.confidence)

print()
print("Patch Required:")
print(patch.patch_required)

print()
print("Can Reproduce:")
print(patch.can_reproduce)

print()
print("Old Code:")
print(patch.old_code)

print()
print("New Code:")
print(patch.new_code)

print()
print("Explanation:")
print(patch.explanation)

print()
print("Recommended Tests:")

for test in patch.tests:
    print("  -", test)

print()
print("=" * 70)
print("                 LLM TEST FINISHED")
print("=" * 70)
