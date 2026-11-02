using Sample.Library;
using Xunit;

namespace Sample.Tests;

public sealed class CalculatorTests
{
    [Fact]
    public void Add_returns_the_sum()
    {
        Assert.Equal(5, Calculator.Add(2, 3));
    }
}
