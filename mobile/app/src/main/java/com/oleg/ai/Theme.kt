package com.oleg.ai

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// Графитовая основа и деликатные жемчужно-розовые акценты.
private val Graphite = Color(0xFF0E0F11)
private val Panel = Color(0xFF191A1E)
private val PanelHigh = Color(0xFF23252A)
private val Pearl = Color(0xFFE9B8CC)
private val Lavender = Color(0xFFB9AECF)
private val TextMain = Color(0xFFECEAF0)
private val TextDim = Color(0xFFA7A5AF)

private val Scheme = darkColorScheme(
    primary = Pearl,
    onPrimary = Color(0xFF2B1822),
    secondary = Lavender,
    onSecondary = Color(0xFF221B30),
    background = Graphite,
    onBackground = TextMain,
    surface = Panel,
    onSurface = TextMain,
    surfaceVariant = PanelHigh,
    onSurfaceVariant = TextDim,
    outline = Color(0xFF3A3C43)
)

private val AppShapes = Shapes(
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp)
)

@Composable
fun OlegTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Scheme, shapes = AppShapes, content = content)
}
