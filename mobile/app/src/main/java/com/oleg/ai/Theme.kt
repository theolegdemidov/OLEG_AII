package com.oleg.ai

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// Графит и приглушённая бронза (цвета сайта).
private val Graphite = Color(0xFF0F0F11)
private val Panel = Color(0xFF17171A)
private val PanelHigh = Color(0xFF222226)
private val Pearl = Color(0xFFD9C3A0)  // бронза с сайта
private val Lavender = Color(0xFFA9A49D)
private val TextMain = Color(0xFFF4EFE8)
private val TextDim = Color(0xFFA9A49D)

private val Scheme = darkColorScheme(
    primary = Pearl,
    onPrimary = Color(0xFF1A140D),
    secondary = Lavender,
    onSecondary = Color(0xFF1A140D),
    background = Graphite,
    onBackground = TextMain,
    surface = Panel,
    onSurface = TextMain,
    surfaceVariant = PanelHigh,
    onSurfaceVariant = TextDim,
    outline = Color(0xFF2B2B30)
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
